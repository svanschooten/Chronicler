"""Assembling a ready-to-run WorkerManager."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.config import Settings
from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import TaskType
from chronicler.core.processing.handlers import WorkerHandlers
from chronicler.core.sqlite import SQLiteChronicleRepository, SQLiteTaskRepository
from chronicler.core.task_events import TaskEventBus
from chronicler.core.workers import WorkerManager


@dataclass
class WorkerRuntime:
    """A WorkerManager plus the session it owns."""

    manager: WorkerManager
    session: AsyncSession


def build_worker_runtime(
    db_manager: DatabaseManager,
    event_bus: TaskEventBus | None = None,
    settings: Settings | None = None,
) -> WorkerRuntime:
    """Builds a WorkerManager with every task handler registered."""
    session = db_manager.get_archive_session()
    manager = WorkerManager(SQLiteTaskRepository(session), event_bus=event_bus)
    handlers = WorkerHandlers(
        db_manager, chronicle_repo=SQLiteChronicleRepository(session), settings=settings
    )
    manager.register_handler(TaskType.IMPORT, handlers.handle_import)
    manager.register_handler(TaskType.CLEAN, handlers.handle_clean)
    manager.register_handler(TaskType.TRANSCRIBE, handlers.handle_transcribe)
    manager.register_handler(TaskType.NORMALIZE, handlers.handle_normalize)
    manager.register_handler(TaskType.SUMMARIZE, handlers.handle_summarize)
    return WorkerRuntime(manager=manager, session=session)
