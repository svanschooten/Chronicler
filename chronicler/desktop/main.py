import asyncio
import logging

from chronicler.core.config import get_settings
from chronicler.core.database_manager import DatabaseManager
from chronicler.desktop.app import run_app


def run_desktop():
    logger = logging.getLogger(__name__)
    logger.info("Chronicler Desktop starting...")
    settings = get_settings()

    if not settings.workspace_path and not settings.server_url:
        logger.error("No workspace or server URL configured. Running configuration wizard...")
        from chronicler.core.wizard import run_wizard
        run_wizard(mode="client:desktop")
        settings = get_settings()

    if not settings.workspace_path:
        # If we are here and workspace_path is missing, it means server_url was set,
        # otherwise the block above would have triggered the wizard.
        print("\nThin Client mode is not yet fully implemented for the Desktop application.")
        print("Please run in Full Stack mode for now (option 1 in the wizard).")
        import sys
        sys.exit(1)

    db_manager = DatabaseManager(settings.workspace_path)

    # Initialize archive database
    asyncio.run(db_manager.init_archive())

    run_app(db_manager)
