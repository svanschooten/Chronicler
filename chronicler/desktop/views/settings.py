import logging

import flet as ft

logger = logging.getLogger(__name__)


class SettingsView(ft.Column):
    def __init__(self):
        logger.debug("SettingsView constructed")
        super().__init__(
            [
                ft.Text("Settings", theme_style=ft.TextThemeStyle.HEADLINE_MEDIUM),
                ft.Divider(),
                ft.Text("Configuration and preferences will be here."),
            ],
            expand=True,
        )

    def did_mount(self):
        logger.debug("SettingsView loaded")

    def will_unmount(self):
        logger.debug("SettingsView unloaded")
