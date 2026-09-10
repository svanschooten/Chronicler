"""Desktop startup: setup wizard, then services, then the app - all in one Flet session."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from chronicler.core.config import Settings
from chronicler.core.handshake import HandshakeError
from chronicler.desktop import main as desktop_main
from tests.chronicler.desktop.controls import text_values


@pytest.fixture
def page():
    return MagicMock()


def runtime_for(settings: Settings, db_manager=None) -> MagicMock:
    runtime = MagicMock()
    runtime.db_manager = db_manager
    runtime.settings = settings
    return runtime


def stub_app(monkeypatch) -> MagicMock:
    app = MagicMock()
    app.return_value.main = AsyncMock()
    monkeypatch.setattr(desktop_main, "DesktopApp", app)
    return app


def stub_wizard(monkeypatch) -> MagicMock:
    wizard = MagicMock()
    wizard.return_value.run = AsyncMock()
    monkeypatch.setattr(desktop_main, "FletSetupWizard", wizard)
    return wizard


# -- the wizard gate ----------------------------------------------------------


@pytest.mark.asyncio
async def test_start_runs_the_wizard_when_the_configuration_is_unusable(
    page, isolated_config, monkeypatch
):
    """
    A packaged build has no console for the wizard in core.wizard to read from, so an
    unconfigured desktop launch has to collect its settings on screen.
    """
    settings = Settings()
    assert not settings.validate_for_mode("client:desktop"), "fixture must start unconfigured"

    wizard = stub_wizard(monkeypatch)
    app = stub_app(monkeypatch)
    monkeypatch.setattr(desktop_main, "get_settings", lambda: settings)
    monkeypatch.setattr(
        desktop_main, "build_runtime", lambda s: runtime_for(s, db_manager=AsyncMock())
    )

    await desktop_main.start(page)

    wizard.assert_called_once_with(page, settings)
    wizard.return_value.run.assert_awaited_once()
    app.return_value.main.assert_awaited_once_with(page)


@pytest.mark.asyncio
async def test_start_skips_the_wizard_when_the_configuration_is_usable(
    page, isolated_config, monkeypatch, tmp_path
):
    settings = Settings(workspace_path=tmp_path, mode="desktop:full_stack")
    wizard = stub_wizard(monkeypatch)
    stub_app(monkeypatch)
    monkeypatch.setattr(desktop_main, "get_settings", lambda: settings)
    monkeypatch.setattr(
        desktop_main, "build_runtime", lambda s: runtime_for(s, db_manager=AsyncMock())
    )

    await desktop_main.start(page)

    wizard.assert_not_called()


@pytest.mark.asyncio
async def test_the_wizard_is_cleared_before_the_app_takes_the_page(
    page, isolated_config, monkeypatch
):
    """Both draw into `page.controls`; without the clean they would stack."""
    settings = Settings()
    stub_wizard(monkeypatch)
    stub_app(monkeypatch)
    monkeypatch.setattr(desktop_main, "get_settings", lambda: settings)
    monkeypatch.setattr(
        desktop_main, "build_runtime", lambda s: runtime_for(s, db_manager=AsyncMock())
    )

    await desktop_main.start(page)

    page.clean.assert_called_once()


# -- services -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_open_services_opens_the_local_databases():
    db_manager = AsyncMock()
    await desktop_main.open_services(runtime_for(Settings(), db_manager=db_manager))

    db_manager.init_archive.assert_awaited_once()


@pytest.mark.asyncio
async def test_open_services_handshakes_with_the_server_for_a_thin_client(monkeypatch):
    handshake = AsyncMock()
    monkeypatch.setattr(desktop_main, "perform_handshake", handshake)
    runtime = runtime_for(Settings(server_url="http://remote", api_key="k"))

    await desktop_main.open_services(runtime)

    handshake.assert_awaited_once_with(runtime.resolver)


# -- failure ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unreachable_server_is_reported_on_screen_rather_than_exiting(
    page, isolated_config, monkeypatch
):
    """
    This used to `sys.exit(1)`. In a windowless build that is a window that flashes up and
    vanishes with nothing said - the user has no way to learn the server was unreachable.
    """
    settings = Settings(server_url="http://remote", api_key="k", mode="desktop:thin_client")
    app = stub_app(monkeypatch)
    monkeypatch.setattr(desktop_main, "get_settings", lambda: settings)
    monkeypatch.setattr(desktop_main, "build_runtime", lambda s: runtime_for(s))
    monkeypatch.setattr(
        desktop_main, "perform_handshake", AsyncMock(side_effect=HandshakeError("server is down"))
    )

    await desktop_main.start(page)

    app.return_value.main.assert_not_awaited()
    shown = text_values(page.add.call_args[0][0])
    assert "server is down" in shown


def test_show_startup_failure_names_the_reason(page):
    desktop_main.show_startup_failure(page, dark_mode=True, message="connection refused")

    assert "connection refused" in text_values(page.add.call_args[0][0])
