"""Assembling a ready-to-run WorkerManager.

Both entry points that run tasks - the desktop app in full-stack mode and the server
- need the exact same wiring, and a handler registered in only one of them is a task
type that silently never runs in the other. This is the one place that mapping lives.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import TaskType
from chronicler.core.processing.handlers import WorkerHandlers
from chronicler.core.sqlite import SQLiteChronicleRepository, SQLiteTaskRepository
from chronicler.core.task_events import TaskEventBus
from chronicler.core.workers import WorkerManager


@dataclass
class WorkerRuntime:
    """A WorkerManager plus the session it owns. The session is handed back rather
    than hidden because whoever starts the worker loop is responsible for closing it
    at shutdown."""

    manager: WorkerManager
    session: AsyncSession


def build_worker_runtime(
    db_manager: DatabaseManager, event_bus: TaskEventBus | None = None
) -> WorkerRuntime:
    """Builds a WorkerManager with every task handler registered.

    The session is dedicated to the worker loop and must never be touched by the UI or
    by HTTP request handling: those run as separate coroutines on the same event loop,
    so an await in either one can interleave with the other's in-flight operation, and
    AsyncSession does not allow that on a shared instance.
    """
    session = db_manager.get_archive_session()
    manager = WorkerManager(SQLiteTaskRepository(session), event_bus=event_bus)
    handlers = WorkerHandlers(db_manager, chronicle_repo=SQLiteChronicleRepository(session))
    manager.register_handler(TaskType.IMPORT, handlers.handle_import)
    manager.register_handler(TaskType.CLEAN, handlers.handle_clean)
    manager.register_handler(TaskType.TRANSCRIBE, handlers.handle_transcribe)
    return WorkerRuntime(manager=manager, session=session)
