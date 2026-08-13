from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.container import Container
from chronicler.core.database_manager import DatabaseManager
from chronicler.core.repositories import ChronicleRepository, TagRepository, TaskRepository
from chronicler.core.sqlite import (
    SQLiteChronicleRepository,
    SQLiteTagRepository,
    SQLiteTaskRepository,
)


def register_local_repositories(container: Container, db_manager: DatabaseManager) -> None:
    """Registrations shared by every local (non-remote) Container - server mode and
    desktop full-stack mode both need the archive session and repository factories
    wired the same way. TranscriptService isn't registered here: it depends on
    DatabaseManager/ChronicleRepository directly rather than a pre-bound repository
    (see transcript_service.py), so it needs no factory of its own - Container builds
    it from what's already registered here.
    """
    container.register_instance(DatabaseManager, db_manager)
    container.register_factory(AsyncSession, lambda: db_manager.get_archive_session())
    # Container.register_factory's generics don't fully accommodate the
    # interface-to-implementation registration pattern it's designed for - mypy treats
    # passing an ABC as the `type[T]` key as if T itself were being instantiated.
    # Pre-existing tension in Container's typing, not something this sprint redesigns.
    container.register_factory(ChronicleRepository, SQLiteChronicleRepository)  # type: ignore[type-abstract]
    container.register_factory(TaskRepository, SQLiteTaskRepository)  # type: ignore[type-abstract]
    container.register_factory(TagRepository, SQLiteTagRepository)  # type: ignore[type-abstract]
