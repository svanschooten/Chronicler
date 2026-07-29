import logging

import flet as ft

logger = logging.getLogger(__name__)


class SettingsView(ft.Column):
    def __init__(self, dark_mode: bool = True):
        logger.debug("SettingsView constructed")
        self.dark_mode = dark_mode

        surface = ft.Colors.BLUE_GREY_700 if dark_mode else ft.Colors.WHITE
        text_color = ft.Colors.WHITE if dark_mode else ft.Colors.BROWN_900
        muted = ft.Colors.BLUE_GREY_200 if dark_mode else ft.Colors.BROWN_500
        border_color = ft.Colors.BLUE_GREY_600 if dark_mode else ft.Colors.AMBER_100

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
                    ft.Switch(value=dark_mode),
                    surface,
                    text_color,
                    muted,
                    border_color,
                ),
                ft.Text("Workspace", size=18, weight=ft.FontWeight.BOLD),
                self.setting_card(
                    "Local workspace",
                    "Not configured",
                    ft.IconButton(icon=ft.Icons.FOLDER_OPEN, icon_color=muted),
                    surface,
                    text_color,
                    muted,
                    border_color,
                ),
                ft.Text("Connection", size=18, weight=ft.FontWeight.BOLD),
                self.setting_card(
                    "Service layer",
                    "Local desktop services are ready to connect.",
                    ft.Text("Local", weight=ft.FontWeight.BOLD, color=ft.Colors.AMBER_300),
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

    def did_mount(self):
        logger.debug("SettingsView loaded")

    def will_unmount(self):
        logger.debug("SettingsView unloaded")
