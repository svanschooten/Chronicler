from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from chronicler.desktop.app import AppState, DesktopApp, ViewType


def test_app_initial_state():
    state = AppState()
    assert state.current_view == ViewType.ARCHIVE


def test_app_navigation():
    state = AppState()
    state.navigate_to(ViewType.TASKS)
    assert state.current_view == ViewType.TASKS


@pytest_asyncio.fixture
async def desktop_app(tmp_path):
    from chronicler.core.database_manager import DatabaseManager

    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()

    app = DesktopApp(db_manager)
    app.page = MagicMock()
    app.content_area = MagicMock()
    app.sidebar = MagicMock()

    yield app

    await db_manager.close_all()


@pytest.mark.asyncio
async def test_worker_session_is_separate_from_view_session(desktop_app):
    """The UI and the background WorkerManager loop are separate coroutines on the
    same event loop; sharing one AsyncSession between them risks
    IllegalStateChangeError if their operations interleave. Confirms they never do.
    """
    desktop_app._worker_session = desktop_app.db_manager.get_archive_session()

    desktop_app.state.navigate_to(ViewType.ARCHIVE)
    await desktop_app.update_view()

    assert desktop_app._view_session is not None
    assert desktop_app._view_session is not desktop_app._worker_session


@pytest.mark.asyncio
async def test_update_view_closes_previous_session_before_opening_next(
    desktop_app, monkeypatch
):
    from sqlalchemy.ext.asyncio import AsyncSession

    close_calls = 0
    original_close = AsyncSession.close

    async def counting_close(self):
        nonlocal close_calls
        close_calls += 1
        await original_close(self)

    monkeypatch.setattr(AsyncSession, "close", counting_close)

    desktop_app.state.navigate_to(ViewType.ARCHIVE)
    await desktop_app.update_view()
    first_session = desktop_app._view_session
    assert close_calls == 0

    desktop_app.state.navigate_to(ViewType.TASKS)
    await desktop_app.update_view()

    assert close_calls == 1
    assert desktop_app._view_session is not first_session


@pytest.mark.asyncio
async def test_settings_view_has_no_session(desktop_app):
    """SettingsView doesn't touch the database at all, so navigating to it shouldn't
    open a session just to immediately hold it open unused.
    """
    desktop_app.state.navigate_to(ViewType.SETTINGS)
    await desktop_app.update_view()

    assert desktop_app._view_session is None


@pytest.mark.asyncio
async def test_cleanup_closes_both_view_and_worker_sessions(desktop_app):
    desktop_app._worker_session = desktop_app.db_manager.get_archive_session()
    desktop_app.worker_manager = MagicMock()

    desktop_app.state.navigate_to(ViewType.ARCHIVE)
    await desktop_app.update_view()

    view_session = desktop_app._view_session
    worker_session = desktop_app._worker_session
    view_session.close = AsyncMock(wraps=view_session.close)
    worker_session.close = AsyncMock(wraps=worker_session.close)

    await desktop_app.cleanup(None)

    view_session.close.assert_awaited_once()
    worker_session.close.assert_awaited_once()
    desktop_app.worker_manager.stop.assert_called_once()
