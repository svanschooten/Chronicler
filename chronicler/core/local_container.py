from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.container import Container
from chronicler.core.database_manager import DatabaseManager
from chronicler.core.repositories import (
    ChronicleRepository,
    KnownSpeakerRepository,
    TagRepository,
    TaskRepository,
)
from chronicler.core.sqlite import (
    SQLiteChronicleRepository,
    SQLiteKnownSpeakerRepository,
    SQLiteTagRepository,
    SQLiteTaskRepository,
)


def register_local_repositories(container: Container, db_manager: DatabaseManager) -> None:
    """
    Registrations shared by every local (non-remote) Container - server mode and desktop
    full-stack mode both need the archive session and repository factories wired the same
    way.
    """
    container.register_instance(DatabaseManager, db_manager)
    container.register_factory(AsyncSession, lambda: db_manager.get_archive_session())
    container.register_factory(ChronicleRepository, SQLiteChronicleRepository)  # type: ignore[type-abstract]
    container.register_factory(TaskRepository, SQLiteTaskRepository)  # type: ignore[type-abstract]
    container.register_factory(TagRepository, SQLiteTagRepository)  # type: ignore[type-abstract]
    container.register_factory(KnownSpeakerRepository, SQLiteKnownSpeakerRepository)  # type: ignore[type-abstract]
