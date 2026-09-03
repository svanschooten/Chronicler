import asyncio
import logging
from pathlib import Path

import uvicorn

from chronicler.core.config import get_settings
from chronicler.core.container import Container
from chronicler.core.database_manager import DatabaseManager
from chronicler.core.local_container import register_local_repositories
from chronicler.core.rpc import RpcServer
from chronicler.core.worker_wiring import build_worker_runtime
from chronicler.core.workers import WorkerManager

logger = logging.getLogger(__name__)


def run_server(host: str = "0.0.0.0", port: int = 8000):
    logger.info("Chronicler Server starting...")
    settings = get_settings()

    if not settings.workspace_path:
        settings.workspace_path = Path.home() / "ChroniclerWorkspace"
        settings.save()

    db_manager = DatabaseManager(settings.workspace_path)

    asyncio.run(db_manager.init_archive())

    container = Container()
    register_local_repositories(container, db_manager)

    from chronicler.core.services import (
        ChronicleService,
        SystemService,
        TaskService,
        TranscriptService,
    )

    rpc_server = RpcServer(
        container,
        services=[
            ChronicleService,
            SystemService,
            TaskService,
            TranscriptService,
        ],
        api_key=settings.api_key,
    )
    app = rpc_server.build()
    logger.info(f"RPC Server API Key: {settings.api_key}")

    worker_manager = build_worker_runtime(db_manager).manager

    asyncio.run(_serve_and_work(app, worker_manager, host, port))


async def _serve_and_work(app, worker_manager: WorkerManager, host: str, port: int) -> None:
    """Runs the HTTP server and the worker loop together on one event loop."""
    config = uvicorn.Config(app, host=host, port=port, log_config=None)
    uvicorn_server = uvicorn.Server(config)
    try:
        await asyncio.gather(uvicorn_server.serve(), worker_manager.run_forever())
    finally:
        worker_manager.stop()
