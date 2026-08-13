import asyncio
import logging

from chronicler.core.config import get_settings
from chronicler.desktop.app import run_app
from chronicler.desktop.runtime import build_runtime


def run_desktop():
    logger = logging.getLogger(__name__)
    logger.info("Chronicler Desktop starting...")
    settings = get_settings()

    if not settings.workspace_path and not settings.server_url:
        logger.error("No workspace or server URL configured. Running configuration wizard...")
        from chronicler.core.wizard import run_wizard

        run_wizard(mode="client:desktop")
        settings = get_settings()

    runtime = build_runtime(settings)

    if runtime.db_manager is not None:
        # Initialize archive database
        asyncio.run(runtime.db_manager.init_archive())

    run_app(runtime)
