"""Assembling a ready-to-run WorkerManager."""

from chronicler.core.config import Settings
from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import TaskType
from chronicler.core.processing.handlers import (
    CleanHandler,
    ImportHandler,
    NormalizeHandler,
    SummarizeHandler,
    TranscribeHandler,
)
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
    importer = ImportHandler(db_manager, settings)
    cleaner = CleanHandler(db_manager, settings)
    transcriber = TranscribeHandler(db_manager, settings)
    normalizer = NormalizeHandler(db_manager, settings)
    summarizer = SummarizeHandler(db_manager, settings)
    manager.register_handler(TaskType.IMPORT, importer.handle_import)
    manager.register_handler(TaskType.CLEAN, cleaner.handle_clean)
    manager.register_handler(TaskType.TRANSCRIBE, transcriber.handle_transcribe)
    manager.register_handler(TaskType.NORMALIZE, normalizer.handle_normalize)
    manager.register_handler(TaskType.SUMMARIZE, summarizer.handle_summarize)
    manager.register_cleanup(TaskType.TRANSCRIBE, transcriber.abandon_transcribe)
    manager.register_cleanup(TaskType.NORMALIZE, normalizer.abandon_normalize)
    return manager
