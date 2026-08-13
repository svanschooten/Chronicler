import asyncio
import logging
from collections.abc import Callable
from enum import Enum

import flet as ft
from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.container import Container
from chronicler.core.models import TaskType
from chronicler.core.processing.handlers import WorkerHandlers
from chronicler.core.remote import RemoteContainer
from chronicler.core.services.chronicle_service import ChronicleService
from chronicler.core.services.task_service import TaskService
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.core.sqlite import SQLiteChronicleRepository, SQLiteTaskRepository
from chronicler.core.task_events import TaskCompletedEvent, TaskEventBus
from chronicler.core.workers import WorkerManager
from chronicler.desktop.components.sidebar import Sidebar
from chronicler.desktop.runtime import DesktopRuntime
from chronicler.desktop.theme import theme_colors
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
    def __init__(self, runtime: DesktopRuntime):
        self.content_area = None
        self.sidebar = None
        self.worker_manager = None
        self.page = None
        self.state = AppState()
        self.runtime = runtime
        self.resolver = runtime.resolver
        # None in thin-client mode - there's no local workspace at all. Used to decide
        # whether this instance owns a WorkerManager (thin client has no local tasks;
        # the server it's pointed at runs its own, see server/main.py).
        self.db_manager = runtime.db_manager
        self.file_stager = runtime.file_stager
        # The Container scope backing whatever view is currently on screen (None for a
        # RemoteContainer resolver, which has no session/scope to manage - each remote
        # call is already scoped per-request server-side). Closed and replaced on
        # every navigation (update_view) rather than held for the app's lifetime - see
        # ASSESSMENT.md §2.1/§2.2. Sequential reuse *within* one view visit is fine
        # (Flet handlers run one at a time); what isn't safe is sharing this with the
        # background worker loop, which gets its own session below.
        self._view_scope: Container | None = None
        # Dedicated to the WorkerManager background loop - never touched by the UI.
        # The UI and the worker loop run as separate coroutines on the same event
        # loop, so an await in either one can interleave with the other's in-flight
        # operation; AsyncSession does not allow that on a shared instance.
        self._worker_session: AsyncSession | None = None
        # Set together with worker_manager in _maybe_start_worker_manager() - both
        # None in thin-client mode. See _on_task_completed for what this is for.
        self.event_bus: TaskEventBus | None = None
        self._unsubscribe_task_events: Callable[[], None] | None = None
        logger.debug("DesktopApp constructed")

    async def main(self, page: ft.Page):
        logger.info("DesktopApp main started")
        self.page = page
        self.page.title = "Chronicler"
        self.page.theme_mode = (
            ft.ThemeMode.DARK if self.runtime.settings.dark_mode else ft.ThemeMode.LIGHT
        )

        self._maybe_start_worker_manager()

        self.page.on_disconnect = self.cleanup
        self.page.on_close = self.cleanup

        # Initialize UI components
        self.sidebar = Sidebar(
            self.on_sidebar_nav_change, dark_mode=self.runtime.settings.dark_mode
        )
        self.content_area = ft.Container(
            expand=True,
            padding=30,
            bgcolor=theme_colors(self.runtime.settings.dark_mode).surface,
        )

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

    def _maybe_start_worker_manager(self):
        """Full-stack mode only - thin client has no local tasks to run, the server
        it's pointed at runs its own WorkerManager (see server/main.py). Extracted
        from main() so this decision is testable without needing a real, fully
        page-attached Flet control tree.
        """
        if self.db_manager is None:
            return

        self._worker_session = self.db_manager.get_archive_session()
        worker_task_repo = SQLiteTaskRepository(self._worker_session)
        worker_chronicle_repo = SQLiteChronicleRepository(self._worker_session)

        # Full-stack desktop mode is the one case where the WorkerManager and the UI
        # genuinely share a process/event loop, so a live refresh on task completion
        # is actually achievable here - see _on_task_completed. TaskEventBus itself
        # doesn't know or care that it's desktop-only; a future websocket/SSE-backed
        # implementation for thin-client/web could subscribe the same way once RPC
        # has a push mechanism to build one on (it doesn't today).
        self.event_bus = TaskEventBus()
        self._unsubscribe_task_events = self.event_bus.subscribe(self._on_task_completed)

        self.worker_manager = WorkerManager(worker_task_repo, event_bus=self.event_bus)
        handlers = WorkerHandlers(self.db_manager, chronicle_repo=worker_chronicle_repo)
        self.worker_manager.register_handler(TaskType.IMPORT, handlers.handle_import)
        self.worker_manager.register_handler(TaskType.CLEAN, handlers.handle_clean)
        self.worker_manager.register_handler(TaskType.TRANSCRIBE, handlers.handle_transcribe)

        # Start worker manager in background
        asyncio.create_task(self.worker_manager.run_forever())

    async def _on_task_completed(self, event: TaskCompletedEvent) -> None:
        """Refreshes whatever view is currently on screen if a just-finished task
        could plausibly have changed what it's showing - a chronicle's transcript,
        speaker count, duration, status or tags after import/clean/transcribe, or
        the task list itself. Settings has nothing task-related to refresh.
        """
        if self.state.current_view == ViewType.SETTINGS:
            return
        if (
            self.state.current_view == ViewType.TRANSCRIPT
            and self.state.selected_chronicle is not None
            and event.chronicle_id is not None
            and event.chronicle_id != self.state.selected_chronicle.id
        ):
            return  # a different chronicle's task - nothing on screen changed

        logger.debug(f"Refreshing current view after task {event.task_id} completed")
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

    async def on_dark_mode_change(self, dark_mode: bool):
        self.runtime.settings.dark_mode = dark_mode
        self.runtime.settings.save()
        self.page.theme_mode = ft.ThemeMode.DARK if dark_mode else ft.ThemeMode.LIGHT
        self.content_area.bgcolor = theme_colors(dark_mode).surface
        # The sidebar is built once in main() and, unlike content_area's view, is
        # never naturally reconstructed on navigation - it needs an explicit nudge.
        if self.sidebar is not None:
            self.sidebar.set_dark_mode(dark_mode)
        # Views bake their colors in at construction time (same pattern as
        # SettingsView already used) - rebuild whichever one is on screen now that
        # dark_mode has changed, rather than trying to mutate every control in place.
        await self.update_view()

    async def cleanup(self, e):
        if self.worker_manager is not None:
            self.worker_manager.stop()
        if self._unsubscribe_task_events is not None:
            self._unsubscribe_task_events()
        await self._close_view_scope()
        if self._worker_session is not None:
            await self._worker_session.close()
        if self.db_manager is not None:
            await self.db_manager.close_all()

    async def _close_view_scope(self):
        if self._view_scope is not None and self._view_scope.is_registered(AsyncSession):
            await self._view_scope.resolve(AsyncSession).close()
        self._view_scope = None

    def _new_scope(self) -> Container | RemoteContainer:
        """A fresh resolution scope for the view about to be shown - a real scope
        (fresh session on next resolve) for a local Container, or the RemoteContainer
        itself for thin-client mode, which has no session of its own to keep fresh
        (RpcServer already scopes each call server-side)."""
        if isinstance(self.resolver, Container):
            scope = self.resolver.create_scope()
            self._view_scope = scope
            return scope
        return self.resolver

    async def update_view(self):
        logger.debug(f"Navigating to view: {self.state.current_view}")
        # Whatever the previous view opened, close it before opening what the new
        # view needs - each navigation gets a fresh session rather than accumulating
        # open ones (the project-session path used to leak one per visit) or reusing
        # one for the app's whole lifetime. Scope creation is deliberately per-branch,
        # not unconditional up front - SettingsView doesn't touch the database at all,
        # so it shouldn't cause a session to be opened (and then immediately closed on
        # the next navigation) for no reason.
        await self._close_view_scope()

        dark_mode = self.runtime.settings.dark_mode

        if self.state.current_view == ViewType.ARCHIVE:
            scope = self._new_scope()
            chronicle_service = scope.resolve(ChronicleService)
            task_service = scope.resolve(TaskService)
            transcript_service = scope.resolve(TranscriptService)
            self.content_area.content = ArchiveView(
                chronicle_service,
                task_service,
                self.open_chronicle,
                self.file_stager.stage,
                transcript_service,
                dark_mode=dark_mode,
            )
        elif self.state.current_view == ViewType.TASKS:
            scope = self._new_scope()
            task_service = scope.resolve(TaskService)
            self.content_area.content = TasksView(task_service, dark_mode=dark_mode)
        elif self.state.current_view == ViewType.SETTINGS:
            self.content_area.content = SettingsView(
                self.runtime.settings, self.on_dark_mode_change
            )
        elif self.state.current_view == ViewType.TRANSCRIPT:
            scope = self._new_scope()
            chronicle_service = scope.resolve(ChronicleService)
            service = scope.resolve(TranscriptService)
            transcript_task_service = scope.resolve(TaskService)
            # Re-fetched rather than reusing self.state.selected_chronicle as-is: that's
            # a snapshot from whenever the user navigated here, and TranscriptView
            # bakes speakers_count/duration/status/tags into its UI at construction
            # time from whatever Chronicle it's given - a live refresh after a
            # background task finishes (see _on_task_completed) would otherwise still
            # show stale values.
            chronicle_id = self.state.selected_chronicle.id
            chronicle = await chronicle_service.get_chronicle(chronicle_id)
            if chronicle is None:
                # Deleted out from under this view - go back rather than render a
                # transcript view for a chronicle that no longer exists.
                await self.go_back()
                return
            self.state.selected_chronicle = chronicle
            self.content_area.content = TranscriptView(
                chronicle,
                self.go_back,
                transcript_service=service,
                task_service=transcript_task_service,
                dark_mode=dark_mode,
            )

        self.content_area.update()
        self.page.update()


def run_app(runtime: DesktopRuntime):
    app = DesktopApp(runtime)
    ft.run(app.main)
