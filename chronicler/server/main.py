import asyncio
import logging
import secrets
from pathlib import Path

import uvicorn

from chronicler.core.config import get_settings
from chronicler.core.container import Container
from chronicler.core.database_manager import DatabaseManager
from chronicler.core.local_container import register_local_repositories
from chronicler.core.rpc import RpcServer
from chronicler.core.worker_wiring import build_worker_manager
from chronicler.core.workers import WorkerManager
from chronicler.core.workspace_lock import WorkspaceLockedError, WorkspaceLockUnavailableError

logger = logging.getLogger(__name__)


def run_server(host: str = "0.0.0.0", port: int = 8000):
    logger.info("Chronicler Server starting...")
    settings = get_settings()

    if not settings.workspace_path:
        settings.workspace_path = Path.home() / "ChroniclerWorkspace"
        settings.save()

    if not settings.api_key:
        # Saved, not just generated: the key is never logged, so a key that lived only in
        # this process could not be given to any client. See docs/security.md.
        settings.api_key = secrets.token_urlsafe(32)
        saved_to = settings.save()
        logger.warning(f"No API key was configured; generated one and saved it to {saved_to}")

    db_manager = DatabaseManager(settings.workspace_path)

    try:
        asyncio.run(db_manager.init_archive())
    except (WorkspaceLockedError, WorkspaceLockUnavailableError) as error:
        # A plain message and exit status 1, not a traceback. See docs/storage.md.
        raise SystemExit(str(error)) from error

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
    # Never the key itself: logs get shared. The last characters are enough to tell which
    # key a server expects. See docs/security.md.
    logger.info(f"RPC server API key configured (ends in ...{rpc_server.api_key[-4:]})")

    worker_manager = build_worker_manager(db_manager)

    asyncio.run(_serve_and_work(app, worker_manager, host, port))


async def _serve_and_work(app, worker_manager: WorkerManager, host: str, port: int) -> None:
    """Runs the HTTP server and the worker loop together on one event loop."""
    config = uvicorn.Config(app, host=host, port=port, log_config=None)
    uvicorn_server = uvicorn.Server(config)
    try:
        await asyncio.gather(uvicorn_server.serve(), worker_manager.run_forever())
    finally:
        worker_manager.stop()
