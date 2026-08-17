"""Tests for the server entry point.

Worker wiring itself is covered by tests/chronicler/core/test_worker_wiring.py - what
matters here is that run_server actually drives both the HTTP server and the worker
loop, which it originally didn't.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import Task, TaskStatus, TaskType
from chronicler.core.sqlite import SQLiteTaskRepository
from chronicler.core.worker_wiring import build_worker_runtime
from chronicler.server.main import _serve_and_work


@pytest.mark.asyncio
async def test_serve_and_work_runs_both_the_server_and_the_worker_loop():
    """run_server() used to never create a WorkerManager at all - queued tasks on a
    server were never executed. uvicorn.run() is synchronous and owns its own event
    loop, so running a worker loop alongside it means driving uvicorn's async Server
    API directly, on the same loop as the worker.
    """
    worker_manager = MagicMock()  # .stop() is sync on the real WorkerManager
    worker_manager.run_forever = AsyncMock()

    with patch("chronicler.server.main.uvicorn.Server") as mock_server_cls:
        mock_server = mock_server_cls.return_value
        mock_server.serve = AsyncMock()

        await _serve_and_work(app=object(), worker_manager=worker_manager, host="x", port=1)

        mock_server.serve.assert_awaited_once()
        worker_manager.run_forever.assert_awaited_once()
        worker_manager.stop.assert_called_once()


@pytest.mark.asyncio
async def test_serve_and_work_stops_the_worker_even_if_the_server_fails():
    worker_manager = MagicMock()
    worker_manager.run_forever = AsyncMock()

    with patch("chronicler.server.main.uvicorn.Server") as mock_server_cls:
        mock_server_cls.return_value.serve = AsyncMock(side_effect=RuntimeError("port in use"))

        with pytest.raises(RuntimeError):
            await _serve_and_work(app=object(), worker_manager=worker_manager, host="x", port=1)

    worker_manager.stop.assert_called_once()


@pytest.mark.asyncio
async def test_a_queued_task_actually_executes_on_a_server(tmp_path):
    """End-to-end: a task queued the same way TaskService.queue_import would (via the
    repository directly, to avoid needing a real file on disk) gets picked up and run by
    the worker manager the server builds.
    """
    db_manager = DatabaseManager(tmp_path)
    runtime = None
    try:
        await db_manager.init_archive()
        runtime = build_worker_runtime(db_manager)

        async with db_manager.get_archive_session() as session:
            task = await SQLiteTaskRepository(session).create(
                Task(type=TaskType.CLEAN, chronicle_id=uuid4())
            )

        # One poll cycle directly, rather than the infinite run_forever() loop.
        await runtime.manager.process_tasks()

        async with db_manager.get_archive_session() as session:
            fetched = await SQLiteTaskRepository(session).get_by_id(task.id)
            # CLEAN on a chronicle with no project data yet still runs the handler; what
            # matters here is that it was picked up and executed at all (status moved
            # off PENDING), not the specific outcome.
            assert fetched.status != TaskStatus.PENDING
    finally:
        if runtime is not None:
            await runtime.session.close()
        await db_manager.close_all()
