"""Tests for build_worker_runtime."""

import pytest

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import TaskType
from chronicler.core.task_events import TaskEventBus
from chronicler.core.worker_wiring import build_worker_runtime


@pytest.mark.asyncio
async def test_registers_every_implemented_task_type(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    try:
        await db_manager.init_archive()

        runtime = build_worker_runtime(db_manager)

        assert set(runtime.manager.handlers) == {
            TaskType.IMPORT,
            TaskType.CLEAN,
            TaskType.TRANSCRIBE,
            TaskType.NORMALIZE,
            TaskType.SUMMARIZE,
        }
    finally:
        await runtime.session.close()
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_each_runtime_gets_its_own_session(tmp_path):
    """
    The worker loop's session must be separate from anything else on the same event loop -
    see build_worker_runtime's docstring.
    """
    db_manager = DatabaseManager(tmp_path)
    try:
        await db_manager.init_archive()

        first = build_worker_runtime(db_manager)
        second = build_worker_runtime(db_manager)

        assert first.session is not second.session
        assert first.manager.repository.session is first.session  # type: ignore[attr-defined]
    finally:
        await first.session.close()
        await second.session.close()
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_event_bus_is_optional_and_forwarded_when_given(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    try:
        await db_manager.init_archive()

        without = build_worker_runtime(db_manager)
        assert without.manager.event_bus is None

        bus = TaskEventBus()
        with_bus = build_worker_runtime(db_manager, event_bus=bus)
        assert with_bus.manager.event_bus is bus
    finally:
        await without.session.close()
        await with_bus.session.close()
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_handlers_share_one_chronicle_repository_session(tmp_path):
    """
    All three handlers come off one WorkerHandlers instance, so they share the archive
    session the runtime owns - not one session each.
    """
    db_manager = DatabaseManager(tmp_path)
    try:
        await db_manager.init_archive()

        runtime = build_worker_runtime(db_manager)

        handler_selves = {
            handler.__self__
            for handler in runtime.manager.handlers.values()  # type: ignore[attr-defined]
        }
        assert len(handler_selves) == 1
        (handlers,) = handler_selves
        assert handlers.chronicle_repo.session is runtime.session
    finally:
        await runtime.session.close()
        await db_manager.close_all()


def test_settings_reach_the_handlers(tmp_path):
    from chronicler.core.config import Settings

    settings = Settings()
    settings.cleaning.hallucination_phrases = ["custom phrase"]
    runtime = build_worker_runtime(DatabaseManager(tmp_path), settings=settings)

    handler = runtime.manager.handlers[TaskType.CLEAN]

    assert handler.__self__.settings.cleaning.hallucination_phrases == ["custom phrase"]


def test_settings_default_to_the_process_configuration(tmp_path):
    runtime = build_worker_runtime(DatabaseManager(tmp_path))

    handler = runtime.manager.handlers[TaskType.CLEAN]

    assert handler.__self__.settings is not None
