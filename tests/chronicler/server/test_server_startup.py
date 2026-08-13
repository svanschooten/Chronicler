from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import Task, TaskStatus, TaskType
from chronicler.server.main import _build_worker_manager, _serve_and_work


@pytest.mark.asyncio
async def test_build_worker_manager_registers_import_and_clean_handlers(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    try:
        await db_manager.init_archive()

        worker_manager = _build_worker_manager(db_manager)

        assert TaskType.IMPORT in worker_manager.handlers
        assert TaskType.CLEAN in worker_manager.handlers
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_build_worker_manager_uses_its_own_session(tmp_path):
    """The worker loop's session must be separate from anything else - see
    ASSESSMENT.md §2.1. Confirmed indirectly: two calls each get their own session-
    backed repository, not a shared one.
    """
    db_manager = DatabaseManager(tmp_path)
    try:
        await db_manager.init_archive()

        worker_manager_a = _build_worker_manager(db_manager)
        worker_manager_b = _build_worker_manager(db_manager)

        session_a = worker_manager_a.repository.session  # type: ignore[attr-defined]
        session_b = worker_manager_b.repository.session  # type: ignore[attr-defined]
        assert session_a is not session_b
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_serve_and_work_runs_both_the_server_and_the_worker_loop():
    """Before this sprint, run_server() never created a WorkerManager at all -
    queued tasks on a server were never executed. Confirms both coroutines actually
    run concurrently rather than one blocking the other.
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
async def test_queued_task_actually_executes_on_a_server(tmp_path):
    """End-to-end: a task queued the same way TaskService.queue_import would (via
    the repository directly, to avoid needing a real file on disk) gets picked up and
    run by the worker manager server/main.py now builds.
    """
    db_manager = DatabaseManager(tmp_path)
    try:
        await db_manager.init_archive()

        worker_manager = _build_worker_manager(db_manager)

        archive_session = db_manager.get_archive_session()
        async with archive_session:
            from chronicler.core.sqlite import SQLiteTaskRepository

            repo = SQLiteTaskRepository(archive_session)
            task = await repo.create(Task(type=TaskType.CLEAN, chronicle_id=uuid4()))

        # Run one poll cycle directly rather than the infinite run_forever() loop.
        await worker_manager.process_tasks()

        async with db_manager.get_archive_session() as check_session:
            from chronicler.core.sqlite import SQLiteTaskRepository as _Repo

            fetched = await _Repo(check_session).get_by_id(task.id)
            # CLEAN on a chronicle with no project data yet still runs the handler;
            # what matters here is that it was picked up and executed at all
            # (status moved off PENDING), not the specific outcome.
            assert fetched.status != TaskStatus.PENDING
    finally:
        await worker_manager.repository.session.close()  # type: ignore[attr-defined]
        await db_manager.close_all()
