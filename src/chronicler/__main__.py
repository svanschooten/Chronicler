import asyncio
from pathlib import Path

from chronicler.core.config import get_settings
from chronicler.core.database_manager import DatabaseManager


def main():
    print("Chronicler Desktop starting...")
    settings = get_settings()

    if not settings.workspace_path:
        # For now, default to a folder in home directory
        settings.workspace_path = Path.home() / "ChroniclerWorkspace"
        print(f"No workspace set. Using default: {settings.workspace_path}")
        settings.save()

    db_manager = DatabaseManager(settings.workspace_path)

    # Initialize archive database
    asyncio.run(db_manager.init_archive())

    from chronicler.desktop.app import run_app

    run_app(db_manager)


def server_main():
    print("Chronicler Server starting...")
    # TODO: Initialize and run FastAPI server
    pass


if __name__ == "__main__":
    main()
