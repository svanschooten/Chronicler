import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.config import Settings
from chronicler.desktop.app import DesktopApp
from chronicler.desktop.runtime import build_runtime
from chronicler.desktop.state import ViewType


@pytest_asyncio.fixture
async def desktop_app(tmp_path):
    settings = Settings(workspace_path=tmp_path, mode="desktop:full_stack")
    runtime = build_runtime(settings)
    await runtime.db_manager.init_archive()

    app = DesktopApp(runtime)
    app.page = MagicMock()
    app.content_area = MagicMock()
    app.sidebar = MagicMock()

    yield app

    await runtime.db_manager.close_all()


@pytest.mark.asyncio
async def test_worker_session_is_separate_from_view_session(desktop_app):
    """
    The UI and the background WorkerManager loop are separate coroutines on the same event
    loop; sharing one AsyncSession between them risks IllegalStateChangeError if their
    operations interleave.
    """
    desktop_app._worker_session = desktop_app.db_manager.get_archive_session()

    desktop_app.state.navigate_to(ViewType.ARCHIVE)
    await desktop_app.update_view()

    assert desktop_app._view_scope is not None
    view_session = desktop_app._view_scope.resolve(AsyncSession)
    assert view_session is not desktop_app._worker_session


@pytest.mark.asyncio
async def test_update_view_closes_previous_session_before_opening_next(desktop_app, monkeypatch):
    close_calls = 0
    original_close = AsyncSession.close

    async def counting_close(self):
        nonlocal close_calls
        close_calls += 1
        await original_close(self)

    monkeypatch.setattr(AsyncSession, "close", counting_close)

    desktop_app.state.navigate_to(ViewType.ARCHIVE)
    await desktop_app.update_view()
    first_scope = desktop_app._view_scope
    first_session = first_scope.resolve(AsyncSession)
    assert close_calls == 0

    desktop_app.state.navigate_to(ViewType.TASKS)
    await desktop_app.update_view()

    assert close_calls == 1
    assert desktop_app._view_scope is not first_scope
    assert desktop_app._view_scope.resolve(AsyncSession) is not first_session


@pytest.mark.asyncio
async def test_settings_view_has_no_session(desktop_app):
    """
    SettingsView doesn't touch the database at all, so navigating to it shouldn't open a
    session just to immediately hold it open unused.
    """
    desktop_app.state.navigate_to(ViewType.SETTINGS)
    await desktop_app.update_view()

    assert desktop_app._view_scope is None


@pytest.mark.asyncio
async def test_cleanup_closes_both_view_and_worker_sessions(desktop_app):
    desktop_app._worker_session = desktop_app.db_manager.get_archive_session()
    desktop_app.worker_manager = MagicMock()

    desktop_app.state.navigate_to(ViewType.ARCHIVE)
    await desktop_app.update_view()

    view_session = desktop_app._view_scope.resolve(AsyncSession)
    worker_session = desktop_app._worker_session
    view_session.close = AsyncMock(wraps=view_session.close)
    worker_session.close = AsyncMock(wraps=worker_session.close)

    await desktop_app.cleanup(None)

    view_session.close.assert_awaited_once()
    worker_session.close.assert_awaited_once()
    desktop_app.worker_manager.stop.assert_called_once()


def test_thin_client_does_not_start_a_worker_manager():
    """
    Thin client has no local tasks to run - the server it's pointed at runs its own
    WorkerManager (Sprint 3 item 4).
    """
    settings = Settings(server_url="http://upstream", api_key="key", mode="desktop:thin_client")
    runtime = build_runtime(settings)
    assert runtime.db_manager is None

    app = DesktopApp(runtime)
    app._maybe_start_worker_manager()

    assert app.worker_manager is None
    assert app._worker_session is None


@pytest.mark.asyncio
async def test_full_stack_starts_a_worker_manager(desktop_app, monkeypatch):
    def fake_create_task(coro):
        coro.close()
        return MagicMock()

    monkeypatch.setattr(asyncio, "create_task", fake_create_task)

    desktop_app._maybe_start_worker_manager()

    assert desktop_app.worker_manager is not None
    assert desktop_app._worker_session is not None


@pytest.mark.asyncio
async def test_on_dark_mode_change_updates_page_and_persists(desktop_app, monkeypatch):
    save_mock = MagicMock()
    monkeypatch.setattr(type(desktop_app.runtime.settings), "save", save_mock)

    await desktop_app.on_dark_mode_change(False)

    assert desktop_app.runtime.settings.dark_mode is False
    save_mock.assert_called_once()
    from flet import ThemeMode

    assert desktop_app.page.theme_mode == ThemeMode.LIGHT
    desktop_app.page.update.assert_called()


@pytest.mark.asyncio
async def test_on_dark_mode_change_repaints_everything_the_app_owns(desktop_app, monkeypatch):
    """
    The sidebar and content area paint themselves, but `page.bgcolor` is what shows behind
    and around them (SafeArea insets, and any gap while a view is rebuilding) - it was never
    set at all, so that area used Flet's default instead of the theme surface.
    """
    from chronicler.desktop.theme import theme_colors

    monkeypatch.setattr(type(desktop_app.runtime.settings), "save", MagicMock())
    desktop_app.divider = MagicMock()

    await desktop_app.on_dark_mode_change(False)

    light = theme_colors(False)
    assert desktop_app.page.bgcolor == light.surface
    assert desktop_app.content_area.bgcolor == light.surface
    assert desktop_app.divider.color == light.border

    await desktop_app.on_dark_mode_change(True)

    dark = theme_colors(True)
    assert desktop_app.page.bgcolor == dark.surface
    assert desktop_app.divider.color == dark.border


def test_apply_theme_tolerates_controls_that_do_not_exist_yet():
    """
    main() calls it before content_area and the divider are built, so it has to cope with a
    partially constructed app.
    """
    from chronicler.core.config import Settings
    from chronicler.desktop.theme import theme_colors

    app = DesktopApp(
        build_runtime(Settings(server_url="http://x", api_key="k", mode="desktop:thin_client"))
    )
    app.page = MagicMock()

    app._apply_theme(False)

    assert app.page.bgcolor == theme_colors(False).surface


@pytest.mark.asyncio
async def test_on_dark_mode_change_rebuilds_current_view_with_new_colors(desktop_app, monkeypatch):
    """
    Regression test: toggling dark mode used to only flip page.theme_mode - the content_area
    background and every view's hardcoded colors stayed exactly as dark as before, since
    views bake their colors in at construction time and nothing rebuilt them.
    """
    monkeypatch.setattr(type(desktop_app.runtime.settings), "save", MagicMock())

    await desktop_app.on_dark_mode_change(False)

    from chronicler.desktop.theme import theme_colors

    assert desktop_app.content_area.bgcolor == theme_colors(False).surface
    assert desktop_app.content_area.content.colors == theme_colors(False)


async def _create_chronicle(desktop_app, title: str):
    """
    A throwaway scope just to create a test fixture, closed immediately after - unlike
    desktop_app._view_scope (torn down by update_view()/cleanup()), a scope created ad hoc
    in a test body is otherwise never closed, and SQLAlchemy warns about the abandoned
    connection when it's garbage collected.
    """
    from chronicler.core.services.chronicle_service import ChronicleService

    scope = desktop_app._new_scope()
    chronicle = await scope.resolve(ChronicleService).create_chronicle(title)
    await scope.resolve(AsyncSession).close()
    return chronicle


@pytest.mark.asyncio
async def test_maybe_start_worker_manager_wires_event_bus(desktop_app, monkeypatch):
    monkeypatch.setattr(asyncio, "create_task", lambda coro: (coro.close(), MagicMock())[1])

    desktop_app._maybe_start_worker_manager()

    from chronicler.core.task_events import TaskEventBus

    assert isinstance(desktop_app.event_bus, TaskEventBus)
    assert desktop_app.worker_manager.event_bus is desktop_app.event_bus


@pytest.mark.asyncio
async def test_on_task_completed_refreshes_transcript_view_for_matching_chronicle(desktop_app):
    from chronicler.core.models import TaskStatus, TaskType
    from chronicler.core.task_events import TaskCompletedEvent

    chronicle = await _create_chronicle(desktop_app, "Recording")

    desktop_app.state.navigate_to(ViewType.TRANSCRIPT, chronicle)
    await desktop_app.update_view()
    view_before = desktop_app.content_area.content

    await desktop_app._on_task_completed(
        TaskCompletedEvent(
            task_id=chronicle.id,
            task_type=TaskType.TRANSCRIBE,
            status=TaskStatus.DONE,
            chronicle_id=chronicle.id,
        )
    )

    assert desktop_app.content_area.content is not view_before


@pytest.mark.asyncio
async def test_on_task_completed_skips_refresh_for_a_different_chronicle(desktop_app):
    from uuid import uuid4

    from chronicler.core.models import TaskStatus, TaskType
    from chronicler.core.task_events import TaskCompletedEvent

    chronicle = await _create_chronicle(desktop_app, "Recording")

    desktop_app.state.navigate_to(ViewType.TRANSCRIPT, chronicle)
    await desktop_app.update_view()
    view_before = desktop_app.content_area.content

    await desktop_app._on_task_completed(
        TaskCompletedEvent(
            task_id=uuid4(),
            task_type=TaskType.TRANSCRIBE,
            status=TaskStatus.DONE,
            chronicle_id=uuid4(),
        )
    )

    assert desktop_app.content_area.content is view_before


@pytest.mark.asyncio
async def test_on_task_completed_skips_settings_view(desktop_app):
    from uuid import uuid4

    from chronicler.core.models import TaskStatus, TaskType
    from chronicler.core.task_events import TaskCompletedEvent

    desktop_app.state.navigate_to(ViewType.SETTINGS)
    await desktop_app.update_view()
    view_before = desktop_app.content_area.content

    await desktop_app._on_task_completed(
        TaskCompletedEvent(
            task_id=uuid4(), task_type=TaskType.IMPORT, status=TaskStatus.DONE, chronicle_id=None
        )
    )

    assert desktop_app.content_area.content is view_before


@pytest.mark.asyncio
async def test_update_view_transcript_refetches_chronicle(desktop_app):
    """
    Regression target: TranscriptView bakes speakers_count/duration/status/tags into its UI
    at construction time from whatever Chronicle object it's given - reusing
    state.selected_chronicle as-is (a snapshot from whenever the user navigated here) would
    keep showing stale values after a background task (e.g. transcription) changes the
    chronicle.
    """
    from chronicler.core.services.chronicle_service import ChronicleService

    chronicle = await _create_chronicle(desktop_app, "Recording")

    desktop_app.state.navigate_to(ViewType.TRANSCRIPT, chronicle)
    await desktop_app.update_view()
    assert desktop_app.content_area.content.chronicle.duration is None

    chronicle_service = desktop_app._view_scope.resolve(ChronicleService)
    chronicle.duration = "1h 0m"
    await chronicle_service.update_chronicle(chronicle)

    await desktop_app.update_view()

    assert desktop_app.content_area.content.chronicle.duration == "1h 0m"
    assert desktop_app.state.selected_chronicle.duration == "1h 0m"


@pytest.mark.asyncio
async def test_update_view_transcript_goes_back_if_chronicle_was_deleted(desktop_app):
    from chronicler.core.services.chronicle_service import ChronicleService

    chronicle = await _create_chronicle(desktop_app, "Doomed")
    desktop_app.state.navigate_to(ViewType.TRANSCRIPT, chronicle)

    scope = desktop_app._new_scope()
    await scope.resolve(ChronicleService).delete_chronicle(chronicle.id)
    await scope.resolve(AsyncSession).close()
    desktop_app._view_scope = None

    await desktop_app.update_view()

    assert desktop_app.state.current_view == ViewType.ARCHIVE


@pytest.mark.asyncio
async def test_thin_client_resolves_a_working_remote_service(tmp_path):
    """
    DesktopApp resolved through a RemoteContainer must get a proxy that actually round-trips
    to a live server, not just an object of the right type.
    """
    from httpx import ASGITransport, AsyncClient

    from chronicler.core.container import Container
    from chronicler.core.database_manager import DatabaseManager
    from chronicler.core.local_container import register_local_repositories
    from chronicler.core.models import Chronicle
    from chronicler.core.rpc import RpcServer
    from chronicler.core.services import ChronicleService
    from chronicler.core.sqlite import SQLiteChronicleRepository

    upstream_db_manager = DatabaseManager(tmp_path)
    await upstream_db_manager.init_archive()
    upstream_container = Container()
    register_local_repositories(upstream_container, upstream_db_manager)

    archive_session = upstream_db_manager.get_archive_session()
    async with archive_session:
        await SQLiteChronicleRepository(archive_session).create(Chronicle(title="Remote One"))

    upstream_app = RpcServer(upstream_container, services=[ChronicleService], api_key="key").build()

    try:
        settings = Settings(server_url="http://upstream", api_key="key", mode="desktop:thin_client")
        runtime = build_runtime(settings)
        app = DesktopApp(runtime)

        transport = ASGITransport(app=upstream_app)
        async with AsyncClient(transport=transport, base_url="http://upstream") as client:
            runtime.resolver._client = client  # type: ignore[attr-defined]
            scope = app._new_scope()
            chronicle_service = scope.resolve(ChronicleService)
            chronicles = await chronicle_service.list_chronicles()

        assert len(chronicles) == 1
        assert chronicles[0].title == "Remote One"
    finally:
        await upstream_db_manager.close_all()


@pytest.mark.asyncio
async def test_refresh_models_caches_the_provider_listing(tmp_path):
    """
    Model discovery is a network round trip, so it runs once at startup rather than every
    time a summary dialog opens.
    """
    from unittest.mock import AsyncMock

    from chronicler.core.services.system_service import SystemService

    runtime = build_runtime(Settings(workspace_path=tmp_path, mode="desktop:full_stack"))
    app = DesktopApp(runtime)

    system = AsyncMock()
    system.list_models.return_value = ["qwen3", "llama3"]
    original = runtime.resolver.resolve
    runtime.resolver.resolve = lambda cls: system if cls is SystemService else original(cls)

    await app.refresh_models()

    assert app.available_models == ["qwen3", "llama3"]


@pytest.mark.asyncio
async def test_refresh_models_survives_an_unreachable_provider(tmp_path):
    from unittest.mock import AsyncMock

    from chronicler.core.services.system_service import SystemService

    runtime = build_runtime(Settings(workspace_path=tmp_path, mode="desktop:full_stack"))
    app = DesktopApp(runtime)

    system = AsyncMock()
    system.list_models.side_effect = RuntimeError("connection refused")
    original = runtime.resolver.resolve
    runtime.resolver.resolve = lambda cls: system if cls is SystemService else original(cls)

    await app.refresh_models()

    assert app.available_models == []
