from unittest.mock import AsyncMock

import flet as ft
import pytest

from chronicler.core.config import Settings
from chronicler.desktop.views.settings import SettingsView


def _all_text(control) -> list[str]:
    """Recursively collect every ft.Text value in a control tree, so assertions don't
    depend on exact structural nesting."""
    found = []
    if isinstance(control, ft.Text) and control.value:
        found.append(control.value)

    children = []
    content = getattr(control, "content", None)
    if content is not None:
        children.append(content)
    controls = getattr(control, "controls", None)
    if controls:
        children.extend(controls)

    for child in children:
        found.extend(_all_text(child))
    return found


def test_settings_view_shows_real_workspace_path(tmp_path):
    settings = Settings(workspace_path=tmp_path, mode="desktop:full_stack")
    view = SettingsView(settings)

    texts = _all_text(view)
    assert str(tmp_path) in texts
    assert "Not configured" not in texts


def test_settings_view_shows_not_configured_when_no_workspace():
    settings = Settings(workspace_path=None, server_url=None)
    view = SettingsView(settings)

    assert "Not configured" in _all_text(view)


def test_settings_view_shows_thin_client_connection_info():
    settings = Settings(
        server_url="http://example.invalid:8000", api_key="key", mode="desktop:thin_client"
    )
    view = SettingsView(settings)

    texts = _all_text(view)
    assert "http://example.invalid:8000" in texts
    assert "Thin Client" in texts


def test_settings_view_shows_full_stack_connection_info(tmp_path):
    settings = Settings(workspace_path=tmp_path, mode="desktop:full_stack")
    view = SettingsView(settings)

    assert "Full Stack" in _all_text(view)


def test_settings_view_reflects_dark_mode_value():
    settings = Settings(dark_mode=False)
    view = SettingsView(settings)

    switches = [c for c in _flatten(view) if isinstance(c, ft.Switch)]
    assert len(switches) == 1
    assert switches[0].value is False


def _flatten(control):
    yield control
    content = getattr(control, "content", None)
    if content is not None:
        yield from _flatten(content)
    controls = getattr(control, "controls", None)
    if controls:
        for c in controls:
            yield from _flatten(c)


@pytest.mark.asyncio
async def test_dark_mode_switch_calls_callback():
    settings = Settings()
    callback = AsyncMock()
    view = SettingsView(settings, on_dark_mode_change=callback)

    fake_event = type("Event", (), {"control": type("Control", (), {"value": False})()})()
    await view._dark_mode_changed(fake_event)

    callback.assert_awaited_once_with(False)


@pytest.mark.asyncio
async def test_dark_mode_switch_is_a_noop_without_callback():
    settings = Settings()
    view = SettingsView(settings, on_dark_mode_change=None)

    fake_event = type("Event", (), {"control": type("Control", (), {"value": False})()})()
    await view._dark_mode_changed(fake_event)  # must not raise
