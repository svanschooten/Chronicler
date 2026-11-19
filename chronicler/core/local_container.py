from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.container import Container
from chronicler.core.database_manager import DatabaseManager


def register_local_storage(container: Container, db_manager: DatabaseManager) -> None:
    """
    Registrations shared by every local (non-remote) Container - server mode and desktop
    full-stack mode both need the workspace and its archive session wired the same way.
    The SQLite repositories need nothing more: Container builds them from the session.
    """
    container.register_instance(DatabaseManager, db_manager)
    container.register_factory(AsyncSession, lambda: db_manager.get_archive_session())
