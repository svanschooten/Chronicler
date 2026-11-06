"""Assembling a ready-to-run WorkerManager."""

from chronicler.core.config import Settings
from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import TaskType
from chronicler.core.processing.handlers import WorkerHandlers
from chronicler.core.task_events import TaskEventBus
from chronicler.core.workers import WorkerManager


def build_worker_manager(
    db_manager: DatabaseManager,
    event_bus: TaskEventBus | None = None,
    settings: Settings | None = None,
) -> WorkerManager:
    """
    Builds a WorkerManager with every task handler registered. The worker and its handlers
    open short archive sessions as they need them, so there is no session to close.
    """
    manager = WorkerManager(db_manager.get_archive_session, event_bus=event_bus)
    handlers = WorkerHandlers(
        db_manager, archive_sessions=db_manager.get_archive_session, settings=settings
    )
    manager.register_handler(TaskType.IMPORT, handlers.handle_import)
    manager.register_handler(TaskType.CLEAN, handlers.handle_clean)
    manager.register_handler(TaskType.TRANSCRIBE, handlers.handle_transcribe)
    manager.register_handler(TaskType.NORMALIZE, handlers.handle_normalize)
    manager.register_handler(TaskType.SUMMARIZE, handlers.handle_summarize)
    return manager
