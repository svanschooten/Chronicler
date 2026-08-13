import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.config import Settings
from chronicler.desktop.app import AppState, DesktopApp, ViewType
from chronicler.desktop.runtime import build_runtime


def test_app_initial_state():
    state = AppState()
    assert state.current_view == ViewType.ARCHIVE


def test_app_navigation():
    state = AppState()
    state.navigate_to(ViewType.TASKS)
    assert state.current_view == ViewType.TASKS


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
    """The UI and the background WorkerManager loop are separate coroutines on the
    same event loop; sharing one AsyncSession between them risks
    IllegalStateChangeError if their operations interleave. Confirms they never do.
    """
    desktop_app._worker_session = desktop_app.db_manager.get_archive_session()

    desktop_app.state.navigate_to(ViewType.ARCHIVE)
    await desktop_app.update_view()

    assert desktop_app._view_scope is not None
    view_session = desktop_app._view_scope.resolve(AsyncSession)
    assert view_session is not desktop_app._worker_session


@pytest.mark.asyncio
async def test_update_view_closes_previous_session_before_opening_next(
    desktop_app, monkeypatch
):
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
    """SettingsView doesn't touch the database at all, so navigating to it shouldn't
    open a session just to immediately hold it open unused.
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
    """Thin client has no local tasks to run - the server it's pointed at runs its
    own WorkerManager (Sprint 3 item 4)."""
    settings = Settings(server_url="http://upstream", api_key="key", mode="desktop:thin_client")
    runtime = build_runtime(settings)
    assert runtime.db_manager is None

    app = DesktopApp(runtime)
    app._maybe_start_worker_manager()

    assert app.worker_manager is None
    assert app._worker_session is None


@pytest.mark.asyncio
async def test_full_stack_starts_a_worker_manager(desktop_app, monkeypatch):
    # Don't actually start the polling loop - this test only cares that a
    # WorkerManager gets configured, not that it runs. Closing (not just discarding)
    # the coroutine avoids a "was never awaited" warning.
    def fake_create_task(coro):
        coro.close()
        return MagicMock()

    monkeypatch.setattr(asyncio, "create_task", fake_create_task)

    desktop_app._maybe_start_worker_manager()

    assert desktop_app.worker_manager is not None
    assert desktop_app._worker_session is not None


@pytest.mark.asyncio
async def test_on_dark_mode_change_updates_page_and_persists(desktop_app, monkeypatch):
    # Settings.save() writing to disk is already covered by test_config.py; here we
    # only care that on_dark_mode_change calls it, so it doesn't need to actually run.
    # Settings is a pydantic model - it rejects ad-hoc instance attribute assignment,
    # so the class method is patched instead.
    save_mock = MagicMock()
    monkeypatch.setattr(type(desktop_app.runtime.settings), "save", save_mock)

    await desktop_app.on_dark_mode_change(False)

    assert desktop_app.runtime.settings.dark_mode is False
    save_mock.assert_called_once()
    from flet import ThemeMode

    assert desktop_app.page.theme_mode == ThemeMode.LIGHT
    desktop_app.page.update.assert_called()


@pytest.mark.asyncio
async def test_thin_client_resolves_a_working_remote_service(tmp_path):
    """DesktopApp resolved through a RemoteContainer must get a proxy that actually
    round-trips to a live server, not just an object of the right type."""
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

    upstream_app = RpcServer(
        upstream_container, services=[ChronicleService], api_key="key"
    ).build()

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
