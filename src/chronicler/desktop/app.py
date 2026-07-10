from enum import Enum

import flet as ft

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.services import ChronicleService, TaskService
from chronicler.core.sqlite_repository import SQLiteChronicleRepository, SQLiteTaskRepository
from chronicler.desktop.views.archive import ArchiveView
from chronicler.desktop.views.tasks import TasksView


class ViewType(str, Enum):
    ARCHIVE = "archive"
    TASKS = "tasks"
    SETTINGS = "settings"


class AppState:
    def __init__(self):
        self.current_view = ViewType.ARCHIVE

    def navigate_to(self, view: ViewType):
        self.current_view = view


class DesktopApp:
    def __init__(self, db_manager: DatabaseManager):
        self.state = AppState()
        self.db_manager = db_manager

    async def main(self, page: ft.Page):
        self.page = page
        self.page.title = "Chronicler"
        self.page.theme_mode = ft.ThemeMode.DARK

        # We open one session for the lifetime of the application for now
        # In a more complex app, we might want to open sessions per operation
        self.session = self.db_manager.get_archive_session()

        self.chronicle_repo = SQLiteChronicleRepository(self.session)
        self.task_repo = SQLiteTaskRepository(self.session)
        self.chronicle_service = ChronicleService(self.chronicle_repo)
        self.task_service = TaskService(self.task_repo)

        self.rail = ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=100,
            destinations=[
                ft.NavigationRailDestination(
                    icon=ft.Icons.ARCHIVE_OUTLINED,
                    selected_icon=ft.Icons.ARCHIVE,
                    label="Archive",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.TASK_ALT_OUTLINED,
                    selected_icon=ft.Icons.TASK_ALT,
                    label="Tasks",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.SETTINGS_OUTLINED,
                    selected_icon=ft.Icons.SETTINGS,
                    label="Settings",
                ),
            ],
            on_change=self.on_nav_change,
        )

        self.content_area = ft.Container(expand=True, padding=20)

        self.page.add(
            ft.Row(
                [
                    self.rail,
                    ft.VerticalDivider(width=1),
                    self.content_area,
                ],
                expand=True,
            )
        )

        await self.update_view()

    async def on_nav_change(self, e):
        index = e.control.selected_index
        if index == 0:
            self.state.navigate_to(ViewType.ARCHIVE)
        elif index == 1:
            self.state.navigate_to(ViewType.TASKS)
        elif index == 2:
            self.state.navigate_to(ViewType.SETTINGS)
        await self.update_view()

    async def update_view(self):
        if self.state.current_view == ViewType.ARCHIVE:
            self.content_area.content = ArchiveView(self.chronicle_service)
        elif self.state.current_view == ViewType.TASKS:
            self.content_area.content = TasksView(self.task_service)
        elif self.state.current_view == ViewType.SETTINGS:
            self.content_area.content = ft.Column(
                [
                    ft.Text("Settings", style=ft.TextThemeStyle.HEADLINE_MEDIUM),
                    ft.Divider(),
                    ft.Text("Configuration and preferences will be here."),
                ],
                expand=True,
            )

        self.page.update()


def run_app(db_manager: DatabaseManager):
    app = DesktopApp(db_manager)
    ft.app(target=app.main)
