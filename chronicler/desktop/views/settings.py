import logging
from collections.abc import Awaitable, Callable

import flet as ft

from chronicler.core.config import Settings
from chronicler.desktop.theme import theme_colors

logger = logging.getLogger(__name__)


class SettingsView(ft.Column):
    def __init__(
        self,
        settings: Settings,
        on_dark_mode_change: Callable[[bool], Awaitable[None]] | None = None,
    ):
        logger.debug("SettingsView constructed")
        self.settings = settings
        self.on_dark_mode_change = on_dark_mode_change
        dark_mode = settings.dark_mode

        colors = theme_colors(dark_mode)
        surface = colors.card
        text_color = colors.text
        muted = colors.muted
        border_color = colors.border
        accent = colors.accent

        if settings.workspace_path:
            workspace_description = str(settings.workspace_path)
        elif settings.server_url:
            workspace_description = "Not configured (thin client mode)"
        else:
            workspace_description = "Not configured"

        if settings.server_url:
            connection_title = "Remote server"
            connection_description = settings.server_url
            connection_badge = "Thin Client"
        else:
            connection_title = "Service layer"
            connection_description = "Local desktop services are ready to connect."
            connection_badge = "Full Stack"

        super().__init__(
            expand=True,
            spacing=16,
            controls=[
                ft.Text("Settings", size=30, weight=ft.FontWeight.BOLD),
                ft.Text("Preferences for this machine and workspace.", color=muted),
                ft.Text("Appearance", size=18, weight=ft.FontWeight.BOLD),
                self.setting_card(
                    "Dark workspace",
                    "Use a low-light interface while reviewing long transcripts.",
                    ft.Switch(value=dark_mode, on_change=self._dark_mode_changed),
                    surface,
                    text_color,
                    muted,
                    border_color,
                ),
                ft.Text("Workspace", size=18, weight=ft.FontWeight.BOLD),
                self.setting_card(
                    "Local workspace",
                    workspace_description,
                    ft.IconButton(icon=ft.Icons.FOLDER_OPEN, icon_color=muted, disabled=True),
                    surface,
                    text_color,
                    muted,
                    border_color,
                ),
                ft.Text("Connection", size=18, weight=ft.FontWeight.BOLD),
                self.setting_card(
                    connection_title,
                    connection_description,
                    ft.Text(connection_badge, weight=ft.FontWeight.BOLD, color=accent),
                    surface,
                    text_color,
                    muted,
                    border_color,
                ),
            ],
        )

    def setting_card(
        self,
        title: str,
        description: str,
        content: ft.Control,
        surface,
        text_color,
        muted,
        border_color,
    ) -> ft.Container:
        return ft.Container(
            bgcolor=surface,
            padding=ft.Padding.all(18),
            border=ft.Border.all(1, border_color),
            border_radius=12,
            content=ft.Row(
                controls=[
                    ft.Column(
                        expand=True,
                        controls=[
                            ft.Text(title, weight=ft.FontWeight.BOLD, color=text_color),
                            ft.Text(description, color=muted),
                        ],
                    ),
                    content,
                ],
            ),
        )

    async def _dark_mode_changed(self, e):
        if self.on_dark_mode_change is not None:
            await self.on_dark_mode_change(e.control.value)

    def did_mount(self):
        logger.debug("SettingsView loaded")

    def will_unmount(self):
        logger.debug("SettingsView unloaded")
