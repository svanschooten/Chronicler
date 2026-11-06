"""Tests for build_worker_manager."""

import pytest

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import TaskType
from chronicler.core.task_events import TaskEventBus
from chronicler.core.worker_wiring import build_worker_manager


def test_registers_every_implemented_task_type(tmp_path):
    manager = build_worker_manager(DatabaseManager(tmp_path))

    assert set(manager.handlers) == {
        TaskType.IMPORT,
        TaskType.CLEAN,
        TaskType.TRANSCRIBE,
        TaskType.NORMALIZE,
        TaskType.SUMMARIZE,
    }


def test_event_bus_is_optional_and_forwarded_when_given(tmp_path):
    db_manager = DatabaseManager(tmp_path)

    assert build_worker_manager(db_manager).event_bus is None

    bus = TaskEventBus()
    assert build_worker_manager(db_manager, event_bus=bus).event_bus is bus


@pytest.mark.asyncio
async def test_the_worker_and_handlers_open_their_own_archive_sessions(tmp_path):
    """
    Nothing holds a session across tasks: each step opens a fresh one, so a lock timeout
    cannot leave the worker stuck on a session that needs a rollback.
    """
    db_manager = DatabaseManager(tmp_path)
    try:
        await db_manager.init_archive()

        manager = build_worker_manager(db_manager)

        handler_selves = {
            handler.__self__
            for handler in manager.handlers.values()  # type: ignore[attr-defined]
        }
        assert len(handler_selves) == 1
        (handlers,) = handler_selves
        async with manager.sessions() as first, handlers.archive_sessions() as second:
            assert first is not second
    finally:
        await db_manager.close_all()


def test_settings_reach_the_handlers(tmp_path):
    from chronicler.core.config import Settings

    settings = Settings()
    settings.cleaning.hallucination_phrases = ["custom phrase"]
    manager = build_worker_manager(DatabaseManager(tmp_path), settings=settings)

    handler = manager.handlers[TaskType.CLEAN]

    assert handler.__self__.settings.cleaning.hallucination_phrases == ["custom phrase"]


def test_settings_default_to_the_process_configuration(tmp_path):
    manager = build_worker_manager(DatabaseManager(tmp_path))

    handler = manager.handlers[TaskType.CLEAN]

    assert handler.__self__.settings is not None
