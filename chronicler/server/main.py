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

    rpc_server = RpcServer(
        container,
        services=[ChronicleService, SearchService, TaskService, TranscriptService],
        api_key=settings.api_key,
    )
    app = rpc_server.build()
    logger.info(f"RPC Server API Key: {settings.api_key}")

    # Same wiring the desktop app uses in full-stack mode - see build_worker_runtime
    # for why the worker loop gets its own session.
    worker_manager = build_worker_runtime(db_manager).manager

    asyncio.run(_serve_and_work(app, worker_manager, host, port))


async def _serve_and_work(app, worker_manager: WorkerManager, host: str, port: int) -> None:
    """Queued tasks on a server used to never run at all - run_server() never created
    a WorkerManager. uvicorn.run() is synchronous and owns its own event loop, so
    running a worker loop alongside it means driving uvicorn's async Server API
    directly instead, on the same loop as the worker (a second OS thread would need
    its own DatabaseManager/engine, since aiosqlite connections are bound to the event
    loop that created them).
    """
    config = uvicorn.Config(app, host=host, port=port, log_config=None)
    uvicorn_server = uvicorn.Server(config)
    try:
        await asyncio.gather(uvicorn_server.serve(), worker_manager.run_forever())
    finally:
        worker_manager.stop()
