import asyncio
import logging
from enum import Enum
from pathlib import Path

import flet as ft

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import TaskType
from chronicler.core.processing.handlers import WorkerHandlers
from chronicler.core.services.chronicle_service import ChronicleService
from chronicler.core.services.task_service import TaskService
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.core.sqlite import (
    SQLiteChronicleRepository,
    SQLiteTaskRepository,
    SQLiteTranscriptRepository,
)
from chronicler.core.workers import WorkerManager
from chronicler.desktop.components.sidebar import Sidebar
from chronicler.desktop.views.archive import ArchiveView
from chronicler.desktop.views.settings import SettingsView
from chronicler.desktop.views.tasks import TasksView
from chronicler.desktop.views.transcript import TranscriptView

logger = logging.getLogger(__name__)


class ViewType(str, Enum):
    ARCHIVE = "archive"
    TASKS = "tasks"
    SETTINGS = "settings"
    TRANSCRIPT = "transcript"


class AppState:
    def __init__(self):
        self.current_view = ViewType.ARCHIVE
        self.selected_chronicle = None

    def navigate_to(self, view: ViewType, chronicle=None):
        self.current_view = view
        self.selected_chronicle = chronicle


class DesktopApp:
    def __init__(self, db_manager: DatabaseManager):
        self.content_area = None
        self.sidebar = None
        self.worker_manager = None
        self.task_service = None
        self.chronicle_service = None
        self.task_repo = None
        self.chronicle_repo = None
        self.session = None
        self.page = None
        self.state = AppState()
        self.db_manager = db_manager
        logger.debug("DesktopApp constructed")

    async def main(self, page: ft.Page):
        logger.info("DesktopApp main started")
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

        # Initialize worker manager
        self.worker_manager = WorkerManager(self.task_repo)
        handlers = WorkerHandlers(self.db_manager, chronicle_repo=self.chronicle_repo)
        self.worker_manager.register_handler(TaskType.IMPORT, handlers.handle_import)
        self.worker_manager.register_handler(TaskType.CLEAN, handlers.handle_clean)

        # Start worker manager in background
        asyncio.create_task(self.worker_manager.run_forever())

        self.page.on_disconnect = self.cleanup
        self.page.on_close = self.cleanup

        # Initialize UI components
        self.sidebar = Sidebar(self.on_sidebar_nav_change)
        self.content_area = ft.Container(expand=True, padding=30, bgcolor=ft.Colors.BLUE_GREY_800)

        self.page.add(
            ft.SafeArea(
                expand=True,
                content=ft.Row(
                    [
                        self.sidebar,
                        ft.VerticalDivider(width=1, thickness=1, color=ft.Colors.BLACK_26),
                        self.content_area,
                    ],
                    expand=True,
                ),
            )
        )

        await self.update_view()

    async def on_sidebar_nav_change(self, view_id: str):
        if view_id == "archive":
            self.state.navigate_to(ViewType.ARCHIVE)
        elif view_id == "tasks":
            self.state.navigate_to(ViewType.TASKS)
        elif view_id == "settings":
            self.state.navigate_to(ViewType.SETTINGS)
        await self.update_view()

    async def open_chronicle(self, chronicle):
        self.state.navigate_to(ViewType.TRANSCRIPT, chronicle)
        await self.update_view()

    async def go_back(self):
        self.state.navigate_to(ViewType.ARCHIVE)
        await self.update_view()

    async def cleanup(self, e):
        self.worker_manager.stop()
        await self.session.close()
        await self.db_manager.close_all()

    async def update_view(self):
        logger.debug(f"Navigating to view: {self.state.current_view}")
        if self.state.current_view == ViewType.ARCHIVE:
            self.content_area.content = ArchiveView(
                self.chronicle_service, self.task_service, self.open_chronicle
            )
        elif self.state.current_view == ViewType.TASKS:
            self.content_area.content = TasksView(self.task_service)
        elif self.state.current_view == ViewType.SETTINGS:
            self.content_area.content = SettingsView()
        elif self.state.current_view == ViewType.TRANSCRIPT:
            chronicle = self.state.selected_chronicle
            custom_path = Path(chronicle.project_path) if chronicle.project_path else None
            # get_project_session is async, so we need to handle it.
            # But update_view is also async.
            session = await self.db_manager.get_project_session(
                str(chronicle.id), custom_path=custom_path
            )
            repo = SQLiteTranscriptRepository(session)
            service = TranscriptService(repo)
            self.content_area.content = TranscriptView(
                chronicle, self.go_back, transcript_service=service
            )

        self.content_area.update()
        self.page.update()


def run_app(db_manager: DatabaseManager):
    app = DesktopApp(db_manager)
    ft.run(app.main)
