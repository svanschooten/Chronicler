import asyncio
import logging
from collections.abc import Callable

import flet as ft
from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.container import Container
from chronicler.core.models import Chronicle
from chronicler.core.remote import RemoteContainer
from chronicler.core.services.chronicle_service import ChronicleService
from chronicler.core.services.system_service import SystemService
from chronicler.core.services.task_service import TaskService
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.core.task_events import TaskCompletedEvent, TaskEventBus
from chronicler.core.worker_wiring import build_worker_runtime
from chronicler.core.workers import WorkerManager
from chronicler.desktop.components.sidebar import Sidebar
from chronicler.desktop.runtime import DesktopRuntime
from chronicler.desktop.state import AppState, ModelCheck, ViewType
from chronicler.desktop.theme import theme_colors
from chronicler.desktop.views.archive import ArchiveView
from chronicler.desktop.views.settings import SettingsView
from chronicler.desktop.views.tasks import TasksView
from chronicler.desktop.views.transcript import TranscriptView

logger = logging.getLogger(__name__)


async def close_scope(scope: "Container | RemoteContainer | None") -> None:
    """Returns a resolution scope's session to the pool, if it ever built one."""
    if not isinstance(scope, Container) or not scope.is_registered(AsyncSession):
        return
    session = scope.cached(AsyncSession)
    if session is not None:
        await session.close()


class DesktopApp:
    def __init__(self, runtime: DesktopRuntime):
        self.state = AppState()
        self.runtime = runtime
        self.resolver = runtime.resolver
        self.db_manager = runtime.db_manager
        self.file_stager = runtime.file_stager

        self.page: ft.Page | None = None
        self.sidebar: Sidebar | None = None
        self.content_area: ft.Container | None = None
        self.divider: ft.VerticalDivider | None = None

        self.worker_manager: WorkerManager | None = None
        self._worker_task: asyncio.Task | None = None
        self._worker_session: AsyncSession | None = None
        self.event_bus: TaskEventBus | None = None
        self._unsubscribe_task_events: Callable[[], None] | None = None

        self.available_models: list[str] = []
        self.capabilities: set[str] | None = None
        self.model_error: str | None = None
        self._view_scope: Container | None = None
        logger.debug("DesktopApp constructed")

    async def main(self, page: ft.Page):
        logger.info("DesktopApp main started")
        self.page = page
        page.title = "Chronicler"
        self._apply_theme(self.runtime.settings.dark_mode)

        self._maybe_start_worker_manager()
        page.run_task(self.refresh_models)

        page.on_disconnect = self.cleanup
        page.on_close = self.cleanup

        self.sidebar = Sidebar(
            self.on_sidebar_nav_change, dark_mode=self.runtime.settings.dark_mode
        )
        self.content_area = ft.Container(expand=True, padding=30)
        self.divider = ft.VerticalDivider(width=1, thickness=1)
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
        """
        Paints everything the app owns directly, as opposed to the views (which bake
        their colours in at construction and get rebuilt by update_view()).
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
        """
        Full-stack mode only - thin client has no local tasks to run, the server it's
        pointed at runs its own WorkerManager (see server/main.py).
        """
        if self.db_manager is None:
            return

        self.event_bus = TaskEventBus()
        self._unsubscribe_task_events = self.event_bus.subscribe(self._on_task_completed)

        worker_runtime = build_worker_runtime(self.db_manager, event_bus=self.event_bus)
        self.worker_manager = worker_runtime.manager
        self._worker_session = worker_runtime.session

        self._worker_task = asyncio.create_task(self.worker_manager.run_forever())

    async def cleanup(self, e):
        """
        Every session this app opened has to be closed before the engines are disposed.
        One left behind is terminated by the garbage collector at interpreter shutdown,
        which is far too late for the greenlet machinery aiosqlite runs on - see
        docs/troubleshooting.md.
        """
        if self.worker_manager is not None:
            self.worker_manager.stop()
        await self._stop_worker_task()
        if self._unsubscribe_task_events is not None:
            self._unsubscribe_task_events()

        await self._close_view_scope()
        await close_scope(self.resolver)
        if self._worker_session is not None:
            await self._worker_session.close()
            self._worker_session = None
        if self.db_manager is not None:
            await self.db_manager.close_all()

    async def _stop_worker_task(self) -> None:
        """`stop()` only asks the loop to finish its current sleep; this waits for it."""
        task = self._worker_task
        self._worker_task = None
        if task is None or task.done():
            return

        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            logger.debug("Worker task stopped", exc_info=True)

    async def _on_task_completed(self, event: TaskCompletedEvent) -> None:
        """
        Refreshes whatever view is currently on screen if a just-finished task could
        plausibly have changed what it's showing - a chronicle's transcript, speaker
        count, duration, status or tags after import/clean/transcribe, or the task list
        itself.
        """
        if self.state.current_view == ViewType.SETTINGS:
            return
        if (
            self.state.current_view == ViewType.TRANSCRIPT
            and self.state.selected_chronicle is not None
            and event.chronicle_id is not None
            and event.chronicle_id != self.state.selected_chronicle.id
        ):
            return

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
        if self.sidebar is not None:
            self.sidebar.set_dark_mode(dark_mode)
        await self.update_view()

    async def refresh_models(self, refresh: bool = False) -> ModelCheck:
        """
        Asks the service layer what it can do.

        Through a scope of its own, like every other consumer: resolving off the root
        container cached its repository's session there for the life of the process,
        holding an open read transaction that nothing ever closed.

        Both answers are the server's in thin-client mode - its extras and its model
        configuration decide what the buttons here should offer. `capabilities` stays None
        when the call fails, which every consumer reads as "assume it works" rather than
        greying out half the interface over an unrelated network hiccup.

        `refresh` bypasses the model cache, for when the configuration just changed and
        the five-minute-old answer is known to be stale.
        """
        scope = (
            self.resolver.create_scope() if isinstance(self.resolver, Container) else self.resolver
        )
        try:
            system = scope.resolve(SystemService)
            try:
                self.available_models = await system.list_models(refresh=refresh)
                self.model_error = await system.model_error()
            except Exception as error:
                logger.warning("Could not list language models", exc_info=True)
                self.available_models = []
                self.model_error = str(error)

            try:
                self.capabilities = set((await system.get_server_info()).capabilities)
            except Exception:
                logger.warning("Could not read the service layer's capabilities", exc_info=True)
                self.capabilities = None
        finally:
            if scope is not self.resolver:
                await close_scope(scope)

        return ModelCheck(models=list(self.available_models), error=self.model_error)

    async def on_llm_change(self) -> ModelCheck:
        """
        Re-asks the service layer after the language model configuration changed.

        The worker already sees the change - it reads the same cached Settings object the
        settings page edits. What did not was the interface: capabilities and the model
        list were read once at startup, so the summarize button stayed greyed out until
        the next launch. See docs/desktop.md.
        """
        return await self.refresh_models(refresh=True)

    async def on_locale_change(self, _locale: str):
        if self.sidebar is not None:
            self.sidebar.relabel()
        await self.update_view()

    async def _close_view_scope(self):
        await close_scope(self._view_scope)
        self._view_scope = None

    def _new_scope(self) -> Container | RemoteContainer:
        """
        A fresh resolution scope for the view about to be shown - a real scope (fresh
        session on next resolve) for a local Container, or the RemoteContainer itself
        for thin-client mode, which has no session of its own to keep fresh (RpcServer
        already scopes each call server-side).
        """
        if isinstance(self.resolver, Container):
            scope = self.resolver.create_scope()
            self._view_scope = scope
            return scope
        return self.resolver

    async def update_view(self):
        logger.debug(f"Navigating to view: {self.state.current_view}")
        await self._close_view_scope()

        content = await self._build_view()
        if content is None:
            return

        if self.content_area is not None:
            self.content_area.content = content
            self.content_area.update()
        if self.page is not None:
            self.page.update()

    async def _build_view(self) -> ft.Control | None:
        """
        The control for the current view, or None if it couldn't be built and already
        redirected (see the TRANSCRIPT branch).
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
            return SettingsView(
                self.runtime.settings,
                self.on_dark_mode_change,
                self.on_locale_change,
                self.on_llm_change,
            )

        selected = self.state.selected_chronicle
        if selected is None:
            logger.warning("Transcript view requested with no chronicle selected")
            await self.go_back()
            return None

        scope = self._new_scope()
        chronicle = await scope.resolve(ChronicleService).get_chronicle(selected.id)
        if chronicle is None:
            await self.go_back()
            return None

        self.state.selected_chronicle = chronicle
        return TranscriptView(
            chronicle,
            self.go_back,
            transcript_service=scope.resolve(TranscriptService),
            task_service=scope.resolve(TaskService),
            dark_mode=dark_mode,
            chronicle_service=scope.resolve(ChronicleService),
            file_stager=self.runtime.file_stager,
            available_models=lambda: self.available_models,
            model_error=lambda: self.model_error,
            capabilities=(
                None if self.capabilities is None else (lambda: self.capabilities or set())
            ),
            settings=self.runtime.settings,
            on_reload=self.update_view,
        )


def run_app(runtime: DesktopRuntime):
    app = DesktopApp(runtime)
    ft.run(app.main)
