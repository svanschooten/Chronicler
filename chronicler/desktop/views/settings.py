import flet as ft
import logging

logger = logging.getLogger(__name__)

class SettingsView(ft.Column):
    def __init__(self):
        logger.info("SettingsView constructed")
        super().__init__(
            [
                ft.Text("Settings", style=ft.TextThemeStyle.HEADLINE_MEDIUM),
                ft.Divider(),
                ft.Text("Configuration and preferences will be here."),
            ],
            expand=True,
        )

    def did_mount(self):
        logger.info("SettingsView loaded")

    def will_unmount(self):
        logger.info("SettingsView unloaded")
