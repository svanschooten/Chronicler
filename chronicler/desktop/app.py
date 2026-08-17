import asyncio
import logging
from collections.abc import Callable

import flet as ft
from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.container import Container
from chronicler.core.models import Chronicle
from chronicler.core.remote import RemoteContainer
from chronicler.core.services.chronicle_service import ChronicleService
from chronicler.core.services.task_service import TaskService
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.core.task_events import TaskCompletedEvent, TaskEventBus
from chronicler.core.worker_wiring import build_worker_runtime
from chronicler.core.workers import WorkerManager
from chronicler.desktop.components.sidebar import Sidebar
from chronicler.desktop.runtime import DesktopRuntime
from chronicler.desktop.state import AppState, ViewType
from chronicler.desktop.theme import theme_colors
from chronicler.desktop.views.archive import ArchiveView
from chronicler.desktop.views.settings import SettingsView
from chronicler.desktop.views.tasks import TasksView
from chronicler.desktop.views.transcript import TranscriptView

logger = logging.getLogger(__name__)


class DesktopApp:
    def __init__(self, runtime: DesktopRuntime):
        self.state = AppState()
        self.runtime = runtime
        self.resolver = runtime.resolver
        # None in thin-client mode - there's no local workspace at all. Used to decide
        # whether this instance owns a WorkerManager (thin client has no local tasks;
        # the server it's pointed at runs its own, see server/main.py).
        self.db_manager = runtime.db_manager
        self.file_stager = runtime.file_stager

        # Built in main(), once there's a page to attach them to.
        self.page: ft.Page | None = None
        self.sidebar: Sidebar | None = None
        self.content_area: ft.Container | None = None
        # Held rather than built inline so _apply_theme can recolour it - like the
        # sidebar, it's built once and never rebuilt on navigation.
        self.divider: ft.VerticalDivider | None = None

        self.worker_manager: WorkerManager | None = None
        # Dedicated to the WorkerManager background loop - never touched by the UI (see
        # build_worker_runtime). None in thin-client mode.
        self._worker_session: AsyncSession | None = None
        # Set together with worker_manager - both None in thin-client mode. See
        # _on_task_completed for what this is for.
        self.event_bus: TaskEventBus | None = None
        self._unsubscribe_task_events: Callable[[], None] | None = None

        # The Container scope backing whatever view is currently on screen (None for a
        # RemoteContainer resolver, which has no session/scope to manage - each remote
        # call is already scoped per-request server-side). Closed and replaced on every
        # navigation (update_view) rather than held for the app's lifetime. Sequential
        # reuse *within* one view visit is fine (Flet handlers run one at a time); what
        # isn't safe is sharing this with the background worker loop, which gets its
        # own session.
        self._view_scope: Container | None = None
        logger.debug("DesktopApp constructed")

    # -- startup / shutdown ---------------------------------------------------

    async def main(self, page: ft.Page):
        logger.info("DesktopApp main started")
        self.page = page
        page.title = "Chronicler"
        self._apply_theme(self.runtime.settings.dark_mode)

        self._maybe_start_worker_manager()

        page.on_disconnect = self.cleanup
        page.on_close = self.cleanup

        self.sidebar = Sidebar(
            self.on_sidebar_nav_change, dark_mode=self.runtime.settings.dark_mode
        )
        self.content_area = ft.Container(expand=True, padding=30)
        self.divider = ft.VerticalDivider(width=1, thickness=1)
        # Now that content_area and the divider exist, colour them too.
        self._apply_theme(self.runtime.settings.dark_mode)

        page.add(
            ft.SafeArea(
                expand=True,
                content=ft.Row(
                    [self.sidebar, self.divider, self.content_area],
                    expand=True,
                ),
            )
        )

        await self.update_view()

    def _apply_theme(self, dark_mode: bool) -> None:
        """Paints everything the app owns directly, as opposed to the views (which bake
        their colours in at construction and get rebuilt by update_view()).

        `page.bgcolor` matters even though the sidebar and content area both paint
        themselves: it's what shows behind and around them - the SafeArea insets, and any
        gap while a view is being rebuilt - and without it that fell back to Flet's own
        default rather than the theme surface.
        """
        colors = theme_colors(dark_mode)
        if self.page is not None:
            self.page.theme_mode = ft.ThemeMode.DARK if dark_mode else ft.ThemeMode.LIGHT
            self.page.bgcolor = colors.surface
        if self.content_area is not None:
            self.content_area.bgcolor = colors.surface
        if self.divider is not None:
            self.divider.color = colors.border

    def _maybe_start_worker_manager(self):
        """Full-stack mode only - thin client has no local tasks to run, the server it's
        pointed at runs its own WorkerManager (see server/main.py). Extracted from
        main() so this decision is testable without needing a real, fully
        page-attached Flet control tree.
        """
        if self.db_manager is None:
            return

        # Full-stack desktop mode is the one case where the WorkerManager and the UI
        # genuinely share a process/event loop, so a live refresh on task completion is
        # actually achievable here - see _on_task_completed. TaskEventBus itself doesn't
        # know or care that it's desktop-only; a future websocket/SSE-backed
        # implementation for thin-client/web could subscribe the same way once RPC has a
        # push mechanism to build one on (it doesn't today).
        self.event_bus = TaskEventBus()
        self._unsubscribe_task_events = self.event_bus.subscribe(self._on_task_completed)

        worker_runtime = build_worker_runtime(self.db_manager, event_bus=self.event_bus)
        self.worker_manager = worker_runtime.manager
        self._worker_session = worker_runtime.session

        asyncio.create_task(self.worker_manager.run_forever())

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

    # -- navigation -----------------------------------------------------------

    async def _on_task_completed(self, event: TaskCompletedEvent) -> None:
        """Refreshes whatever view is currently on screen if a just-finished task could
        plausibly have changed what it's showing - a chronicle's transcript, speaker
        count, duration, status or tags after import/clean/transcribe, or the task list
        itself. Settings has nothing task-related to refresh.
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
        view = ViewType.from_nav_id(view_id)
        if view is not None:
            self.state.navigate_to(view)
        await self.update_view()

    async def open_chronicle(self, chronicle: Chronicle):
        self.state.navigate_to(ViewType.TRANSCRIPT, chronicle)
        await self.update_view()

    async def go_back(self):
        self.state.navigate_to(ViewType.ARCHIVE)
        await self.update_view()

    async def on_dark_mode_change(self, dark_mode: bool):
        self.runtime.settings.dark_mode = dark_mode
        self.runtime.settings.save()
        self._apply_theme(dark_mode)
        # The sidebar is built once in main() and, unlike content_area's view, is never
        # naturally reconstructed on navigation - it needs an explicit nudge.
        if self.sidebar is not None:
            self.sidebar.set_dark_mode(dark_mode)
        # Views bake their colors in at construction time - rebuild whichever one is on
        # screen now that dark_mode has changed, rather than trying to mutate every
        # control in place.
        await self.update_view()

    # -- view construction ----------------------------------------------------

    async def _close_view_scope(self):
        if self._view_scope is not None and self._view_scope.is_registered(AsyncSession):
            await self._view_scope.resolve(AsyncSession).close()
        self._view_scope = None

    def _new_scope(self) -> Container | RemoteContainer:
        """A fresh resolution scope for the view about to be shown - a real scope (fresh
        session on next resolve) for a local Container, or the RemoteContainer itself for
        thin-client mode, which has no session of its own to keep fresh (RpcServer
        already scopes each call server-side)."""
        if isinstance(self.resolver, Container):
            scope = self.resolver.create_scope()
            self._view_scope = scope
            return scope
        return self.resolver

    async def update_view(self):
        logger.debug(f"Navigating to view: {self.state.current_view}")
        # Whatever the previous view opened, close it before opening what the new view
        # needs - each navigation gets a fresh session rather than accumulating open
        # ones or reusing one for the app's whole lifetime.
        await self._close_view_scope()

        content = await self._build_view()
        if content is None:
            return  # the view declined to render and navigated elsewhere instead

        if self.content_area is not None:
            self.content_area.content = content
            self.content_area.update()
        if self.page is not None:
            self.page.update()

    async def _build_view(self) -> ft.Control | None:
        """The control for the current view, or None if it couldn't be built and
        already redirected (see the TRANSCRIPT branch).

        Scope creation is deliberately per-branch, not unconditional up front -
        SettingsView doesn't touch the database at all, so it shouldn't cause a session
        to be opened (and then immediately closed on the next navigation) for nothing.
        """
        dark_mode = self.runtime.settings.dark_mode

        if self.state.current_view == ViewType.ARCHIVE:
            scope = self._new_scope()
            return ArchiveView(
                scope.resolve(ChronicleService),
                scope.resolve(TaskService),
                self.open_chronicle,
                self.file_stager.stage,
                scope.resolve(TranscriptService),
                dark_mode=dark_mode,
            )

        if self.state.current_view == ViewType.TASKS:
            scope = self._new_scope()
            return TasksView(
                scope.resolve(TaskService),
                scope.resolve(ChronicleService),
                dark_mode=dark_mode,
            )

        if self.state.current_view == ViewType.SETTINGS:
            return SettingsView(self.runtime.settings, self.on_dark_mode_change)

        selected = self.state.selected_chronicle
        if selected is None:
            # Nothing to show a transcript for - only reachable if something navigated
            # to TRANSCRIPT without going through open_chronicle.
            logger.warning("Transcript view requested with no chronicle selected")
            await self.go_back()
            return None

        scope = self._new_scope()
        # Re-fetched rather than reusing self.state.selected_chronicle as-is: that's a
        # snapshot from whenever the user navigated here, and TranscriptView bakes
        # speakers_count/duration/status/tags into its UI at construction time from
        # whatever Chronicle it's given - a live refresh after a background task
        # finishes (see _on_task_completed) would otherwise still show stale values.
        chronicle = await scope.resolve(ChronicleService).get_chronicle(selected.id)
        if chronicle is None:
            # Deleted out from under this view - go back rather than render a transcript
            # view for a chronicle that no longer exists.
            await self.go_back()
            return None

        self.state.selected_chronicle = chronicle
        return TranscriptView(
            chronicle,
            self.go_back,
            transcript_service=scope.resolve(TranscriptService),
            task_service=scope.resolve(TaskService),
            dark_mode=dark_mode,
        )


def run_app(runtime: DesktopRuntime):
    app = DesktopApp(runtime)
    ft.run(app.main)
