import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.config import get_settings
from chronicler.core.container import Container
from chronicler.core.database_manager import DatabaseManager
from chronicler.core.repositories import (
    ChronicleRepository,
    TagRepository,
    TaskRepository,
)
from chronicler.core.rpc import RpcServer
from chronicler.core.sqlite import (
    SQLiteChronicleRepository,
    SQLiteTagRepository,
    SQLiteTaskRepository,
)


def run_server(host: str = "0.0.0.0", port: int = 8000):
    print("Chronicler Server starting...")
    settings = get_settings()

    if not settings.workspace_path:
        settings.workspace_path = Path.home() / "ChroniclerWorkspace"
        settings.save()

    db_manager = DatabaseManager(settings.workspace_path)

    # Initialize archive database
    asyncio.run(db_manager.init_archive())

    container = Container()
    container.register_instance(DatabaseManager, db_manager)
    container.register_factory(AsyncSession, lambda dm: dm.get_archive_session())
    container.register_factory(ChronicleRepository, SQLiteChronicleRepository)
    container.register_factory(TaskRepository, SQLiteTaskRepository)
    container.register_factory(TagRepository, SQLiteTagRepository)

    server = RpcServer(container)
    server.run(host=host, port=port)
