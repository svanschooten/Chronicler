import logging

import flet as ft

from chronicler.core.config import get_settings
from chronicler.core.handshake import HandshakeError, perform_handshake
from chronicler.desktop.app import DesktopApp
from chronicler.desktop.runtime import DesktopRuntime, build_runtime
from chronicler.desktop.theme import theme_colors
from chronicler.desktop.views.wizard import FletSetupWizard
from chronicler.i18n import t

logger = logging.getLogger(__name__)

DESKTOP_MODE = "client:desktop"


def run_desktop():
    logger.info("Chronicler Desktop starting...")
    ft.run(start)


async def start(page: ft.Page) -> None:
    """
    Everything the desktop app needs to come up, in the one Flet session: setup wizard if
    the configuration is not usable yet, then the databases or the server handshake, then
    the app itself.

    Startup used to run before Flet did, with the console wizard and three `asyncio.run()`
    calls in front of `ft.run()`. A packaged build has no console for that wizard to read
    from - and on Windows a windowless executable has no stdio at all - so setup has to
    happen on screen, which means inside the session.
    """
    page.title = "Chronicler"
    settings = get_settings()

    if not settings.validate_for_mode(DESKTOP_MODE):
        logger.info("No usable configuration found; starting the setup wizard")
        await FletSetupWizard(page, settings).run()

    runtime = build_runtime(settings)

    try:
        await open_services(runtime)
    except HandshakeError as error:
        logger.error(str(error))
        show_startup_failure(page, settings.dark_mode, str(error))
        return

    page.clean()
    await DesktopApp(runtime).main(page)


async def open_services(runtime: DesktopRuntime) -> None:
    """Opens the local databases, or proves the configured server is reachable."""
    if runtime.db_manager is not None:
        await runtime.db_manager.init_archive()
        return

    logger.info(f"Thin client starting against {runtime.settings.server_url}")
    await perform_handshake(runtime.resolver)


def show_startup_failure(page: ft.Page, dark_mode: bool, message: str) -> None:
    """
    A handshake failure used to `sys.exit(1)`, which in a windowless build is a window that
    flashes and vanishes with nothing said. This leaves the reason on screen instead.
    """
    colors = theme_colors(dark_mode)
    page.clean()
    page.theme_mode = ft.ThemeMode.DARK if dark_mode else ft.ThemeMode.LIGHT
    page.bgcolor = colors.surface
    page.add(
        ft.Container(
            expand=True,
            bgcolor=colors.surface,
            padding=32,
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.ERROR_OUTLINE, color=colors.accent, size=48),
                    ft.Text(
                        t("startup.failed"),
                        size=22,
                        weight=ft.FontWeight.BOLD,
                        color=colors.text,
                    ),
                    ft.Text(message, color=colors.muted, text_align=ft.TextAlign.CENTER),
                    ft.Text(t("startup.hint"), size=12, color=colors.muted),
                ],
                spacing=12,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
            ),
        )
    )
