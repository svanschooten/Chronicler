import asyncio
import logging
import sys

import flet as ft

from chronicler.core.config import get_settings, reload_settings
from chronicler.core.handshake import HandshakeError, perform_handshake
from chronicler.desktop.app import DesktopApp
from chronicler.desktop.runtime import build_runtime
from chronicler.desktop.views.wizard import SetupWizard

logger = logging.getLogger(__name__)


def run_desktop():
    logger.info("Chronicler Desktop starting...")

    async def main(page: ft.Page):
        page.title = "Chronicler"

        # Check if wizard needed
        settings = get_settings()
        needs_setup = not settings.workspace_path and not settings.server_url

        if needs_setup:

            def on_wizard_complete():
                # Reload settings after wizard saves
                reload_settings()
                # Continue with main app
                page.run_task(start_main_app, page)

            wizard = SetupWizard(page, settings, on_wizard_complete)
            wizard.open()
        else:
            await start_main_app(page)

    async def start_main_app(page: ft.Page):
        settings = get_settings()
        runtime = build_runtime(settings)

        if runtime.db_manager is not None:
            await runtime.db_manager.init_archive()
        else:
            logger.info(f"Thin client starting against {settings.server_url}")
            try:
                await perform_handshake(runtime.resolver)
            except HandshakeError as error:
                logger.error(str(error))
                sys.exit(1)

        app = DesktopApp(runtime)
        await app.main(page)

    ft.run(main)