import asyncio
import logging
from pathlib import Path

from chronicler.core.config import get_settings
from chronicler.core.database_manager import DatabaseManager
from chronicler.desktop.app import run_app


def run_desktop():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)
    logger.info("Chronicler Desktop starting...")
    settings = get_settings()

    if not settings.workspace_path:
        # For now, default to a folder in home directory
        settings.workspace_path = Path.home() / "ChroniclerWorkspace"
        logger.info(f"No workspace set. Using default: {settings.workspace_path}")
        settings.save()

    db_manager = DatabaseManager(settings.workspace_path)

    # Initialize archive database
    asyncio.run(db_manager.init_archive())

    run_app(db_manager)
