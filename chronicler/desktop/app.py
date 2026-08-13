import asyncio
import logging
from enum import Enum
from pathlib import Path

import flet as ft
from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.file_staging import stage_local_file
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
        self.page = None
        self.state = AppState()
        self.db_manager = db_manager
        # The session backing whatever view is currently on screen. Closed and
        # replaced on every navigation (update_view) rather than held for the app's
        # lifetime - see ASSESSMENT.md §2.1/§2.2. Sequential reuse *within* one view
        # visit is fine (Flet handlers run one at a time); what isn't safe is sharing
        # this with the background worker loop, which gets its own session below.
        self._view_session: AsyncSession | None = None
        # Dedicated to the WorkerManager background loop - never touched by the UI.
        # The UI and the worker loop run as separate coroutines on the same event
        # loop, so an await in either one can interleave with the other's in-flight
        # operation; AsyncSession does not allow that on a shared instance.
        self._worker_session: AsyncSession | None = None
        logger.debug("DesktopApp constructed")

    async def main(self, page: ft.Page):
        logger.info("DesktopApp main started")
        self.page = page
        self.page.title = "Chronicler"
        self.page.theme_mode = ft.ThemeMode.DARK

        self._worker_session = self.db_manager.get_archive_session()
        worker_task_repo = SQLiteTaskRepository(self._worker_session)
        worker_chronicle_repo = SQLiteChronicleRepository(self._worker_session)

        self.worker_manager = WorkerManager(worker_task_repo)
        handlers = WorkerHandlers(self.db_manager, chronicle_repo=worker_chronicle_repo)
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
        await self._close_view_session()
        if self._worker_session is not None:
            await self._worker_session.close()
        await self.db_manager.close_all()

    async def _close_view_session(self):
        if self._view_session is not None:
            await self._view_session.close()
            self._view_session = None

    async def stage_file(self, local_path: str) -> str:
        """Passed into ArchiveView so it never has to know whether it's running in
        full-stack (copy to local imports/) or thin-client mode (upload to the
        server's /upload - wired in when DesktopApp moves onto Container/
        RemoteContainer)."""
        staged = stage_local_file(Path(local_path), self.db_manager.get_imports_path())
        return str(staged)

    async def update_view(self):
        logger.debug(f"Navigating to view: {self.state.current_view}")
        # Whatever the previous view opened, close it before opening what the new
        # view needs - each navigation gets a fresh session rather than accumulating
        # open ones (the project-session path used to leak one per visit) or reusing
        # one for the app's whole lifetime.
        await self._close_view_session()

        if self.state.current_view == ViewType.ARCHIVE:
            session = self.db_manager.get_archive_session()
            self._view_session = session
            chronicle_service = ChronicleService(SQLiteChronicleRepository(session))
            task_service = TaskService(SQLiteTaskRepository(session))
            self.content_area.content = ArchiveView(
                chronicle_service, task_service, self.open_chronicle, self.stage_file
            )
        elif self.state.current_view == ViewType.TASKS:
            session = self.db_manager.get_archive_session()
            self._view_session = session
            task_service = TaskService(SQLiteTaskRepository(session))
            self.content_area.content = TasksView(task_service)
        elif self.state.current_view == ViewType.SETTINGS:
            self.content_area.content = SettingsView()
        elif self.state.current_view == ViewType.TRANSCRIPT:
            chronicle = self.state.selected_chronicle
            custom_path = Path(chronicle.project_path) if chronicle.project_path else None
            session = await self.db_manager.get_project_session(
                str(chronicle.id), custom_path=custom_path
            )
            self._view_session = session
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
