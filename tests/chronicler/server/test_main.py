"""Tests for the server entry point."""

import errno
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import yaml

from chronicler.core.config import Settings
from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import Chronicle, Task, TaskStatus, TaskType
from chronicler.core.sqlite import SQLiteChronicleRepository, SQLiteTaskRepository
from chronicler.core.worker_wiring import build_worker_manager
from chronicler.core.workspace_lock import WorkspaceLock
from chronicler.server.main import _serve_and_work, run_server


@pytest.mark.asyncio
async def test_serve_and_work_runs_both_the_server_and_the_worker_loop():
    """
    run_server() used to never create a WorkerManager at all - queued tasks on a server were
    never executed. uvicorn.run() is synchronous and owns its own event loop, so running a
    worker loop alongside it means driving uvicorn's async Server API directly, on the same
    loop as the worker.
    """
    worker_manager = MagicMock()
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
    """
    End-to-end: a task queued the same way TaskService.queue_import would (via the
    repository directly, to avoid needing a real file on disk) gets picked up and run by the
    worker manager the server builds.
    """
    db_manager = DatabaseManager(tmp_path)
    try:
        await db_manager.init_archive()
        worker_manager = build_worker_manager(db_manager)

        chronicle_id = uuid4()
        async with db_manager.get_archive_session() as session:
            await SQLiteChronicleRepository(session).create(
                Chronicle(id=chronicle_id, title="Queued")
            )
            task = await SQLiteTaskRepository(session).create(
                Task(type=TaskType.CLEAN, chronicle_id=chronicle_id)
            )

        await worker_manager.process_tasks()

        async with db_manager.get_archive_session() as session:
            fetched = await SQLiteTaskRepository(session).get_by_id(task.id)
            assert fetched.status != TaskStatus.PENDING
    finally:
        await db_manager.close_all()


def test_a_server_on_a_workspace_open_elsewhere_exits_with_the_reason(
    tmp_path, isolated_config, monkeypatch
):
    """One workspace belongs to one process: a second one stops before serving anything."""
    monkeypatch.setattr(
        "chronicler.server.main.get_settings", lambda: Settings(workspace_path=tmp_path)
    )
    holder = WorkspaceLock(tmp_path)
    holder.acquire()
    try:
        with patch("chronicler.server.main.uvicorn.Server") as mock_server_cls:
            with pytest.raises(SystemExit) as exit_info:
                run_server()
        mock_server_cls.assert_not_called()
    finally:
        holder.release()

    assert "already open in another Chronicler process" in str(exit_info.value.code)


def test_a_server_on_a_workspace_that_cannot_be_locked_exits_with_the_reason(
    tmp_path, isolated_config, monkeypatch
):
    """Ticket 068: the message names the filesystem problem, not another process."""
    monkeypatch.setattr(
        "chronicler.server.main.get_settings", lambda: Settings(workspace_path=tmp_path)
    )

    def no_locks(fd: int) -> None:
        raise OSError(errno.ENOLCK, "No locks available")

    monkeypatch.setattr("chronicler.core.workspace_lock._lock", no_locks)

    with patch("chronicler.server.main.uvicorn.Server") as mock_server_cls:
        with pytest.raises(SystemExit) as exit_info:
            run_server()
    mock_server_cls.assert_not_called()

    message = str(exit_info.value.code)
    assert "No locks available" in message
    assert "already open" not in message


def test_startup_does_not_log_the_api_key(tmp_path, isolated_config, monkeypatch, caplog):
    monkeypatch.setattr(
        "chronicler.server.main.get_settings",
        lambda: Settings(workspace_path=tmp_path, api_key="super-secret-key-1234"),
    )
    with (
        patch("chronicler.server.main.asyncio.run", side_effect=lambda coro: coro.close()),
        caplog.at_level("DEBUG"),
    ):
        run_server()

    assert "super-secret-key" not in caplog.text
    assert "1234" in caplog.text


def test_a_generated_key_is_saved_so_clients_can_use_it(
    tmp_path, isolated_config, monkeypatch, caplog
):
    """Review repro: a key generated at startup was only ever logged as `...weSU`."""
    config_file = isolated_config / "settings.yaml"
    monkeypatch.setenv("CHRONICLER_CONFIG_FILE", str(config_file))
    monkeypatch.setattr(
        "chronicler.server.main.get_settings", lambda: Settings(workspace_path=tmp_path)
    )
    with (
        patch("chronicler.server.main.asyncio.run", side_effect=lambda coro: coro.close()),
        caplog.at_level("INFO"),
    ):
        run_server()

    saved_key = yaml.safe_load(config_file.read_text())["api_key"]
    assert saved_key
    assert saved_key not in caplog.text
    assert f"...{saved_key[-4:]}" in caplog.text
