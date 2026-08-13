import asyncio
import logging
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
    logger = logging.getLogger(__name__)
    logger.info("Chronicler Server starting...")
    settings = get_settings()

    if not settings.workspace_path:
        settings.workspace_path = Path.home() / "ChroniclerWorkspace"
        settings.save()

    db_manager = DatabaseManager(settings.workspace_path)

    # Initialize archive database
    asyncio.run(db_manager.init_archive())

    container = Container()
    container.register_instance(DatabaseManager, db_manager)
    container.register_factory(AsyncSession, lambda: db_manager.get_archive_session())
    # Container.register_factory's generics don't fully accommodate the
    # interface-to-implementation registration pattern it's designed for - mypy treats
    # passing an ABC as the `type[T]` key as if T itself were being instantiated.
    # Pre-existing tension in Container's typing, not something this sprint redesigns.
    container.register_factory(ChronicleRepository, SQLiteChronicleRepository)  # type: ignore[type-abstract]
    container.register_factory(TaskRepository, SQLiteTaskRepository)  # type: ignore[type-abstract]
    container.register_factory(TagRepository, SQLiteTagRepository)  # type: ignore[type-abstract]

    from chronicler.core.services import (
        ChronicleService,
        SearchService,
        TaskService,
        TranscriptService,
    )

    server = RpcServer(
        container,
        services=[ChronicleService, SearchService, TaskService, TranscriptService],
        api_key=settings.api_key,
    )
    server.run(host=host, port=port)
