import asyncio
import logging
from pathlib import Path

from chronicler.core.config import get_settings
from chronicler.core.container import Container
from chronicler.core.database_manager import DatabaseManager
from chronicler.core.local_container import register_local_repositories
from chronicler.core.rpc import RpcServer


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
    register_local_repositories(container, db_manager)

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
