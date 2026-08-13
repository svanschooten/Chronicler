from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import flet as ft
import pytest

from chronicler.desktop.components.sidebar import Sidebar
from chronicler.desktop.theme import theme_colors


def _attach_mock_page(view):
    mock_page = MagicMock(spec=ft.Page)
    patcher = patch.object(Sidebar, "page", new_callable=PropertyMock)
    page_prop = patcher.start()
    page_prop.return_value = mock_page
    return patcher, mock_page


def test_dark_mode_flag_changes_sidebar_colors():
    """Regression test: the sidebar used to hardcode BLUE_GREY_900/700/400/WHITE
    regardless of dark_mode, so it stayed dark even after switching the rest of the
    app to light mode."""
    dark_sidebar = Sidebar(AsyncMock(), dark_mode=True)
    light_sidebar = Sidebar(AsyncMock(), dark_mode=False)

    assert dark_sidebar.bgcolor != light_sidebar.bgcolor
    assert dark_sidebar.colors == theme_colors(True)
    assert light_sidebar.colors == theme_colors(False)


def test_set_dark_mode_rebuilds_colors_and_bgcolor():
    sidebar = Sidebar(AsyncMock(), dark_mode=True)
    patcher, _ = _attach_mock_page(sidebar)

    try:
        sidebar.set_dark_mode(False)
    finally:
        patcher.stop()

    assert sidebar.colors == theme_colors(False)
    assert sidebar.bgcolor == theme_colors(False).sidebar


@pytest.mark.asyncio
async def test_handle_nav_click_calls_on_nav_change_with_view_id():
    on_nav_change = AsyncMock()
    sidebar = Sidebar(on_nav_change)
    patcher, _ = _attach_mock_page(sidebar)
    fake_event = MagicMock(control=MagicMock(data="tasks"))

    try:
        await sidebar.handle_nav_click(fake_event)
    finally:
        patcher.stop()

    assert sidebar.selected_view == "tasks"
    on_nav_change.assert_awaited_once_with("tasks")
