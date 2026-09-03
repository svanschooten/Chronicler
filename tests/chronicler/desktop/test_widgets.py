from unittest.mock import MagicMock

import flet as ft

from chronicler.desktop.widgets import amber_button


def test_amber_button_without_dropdown_has_no_chevron():
    button = amber_button("New Chronicle", ft.Icons.ADD)

    icons = [c for c in button.content.controls if isinstance(c, ft.Icon)]
    assert len(icons) == 1


def test_amber_button_with_dropdown_adds_separator_and_chevron():
    button = amber_button("Import", ft.Icons.ADD, dropdown=True)

    icons = [c for c in button.content.controls if isinstance(c, ft.Icon)]
    assert len(icons) == 2
    assert icons[-1].icon == ft.Icons.EXPAND_MORE


def test_amber_button_wires_on_click():
    handler = MagicMock()
    button = amber_button("New Chronicle", ft.Icons.ADD, on_click=handler)

    assert button.on_click is handler


def test_two_amber_buttons_render_identically_regardless_of_label():
    """
    The concrete fix for "Import and New Chronicle still don't look the same": both now go
    through the same builder, so their Container styling (padding, radius, bgcolor) is
    guaranteed identical, not just coincidentally matching.
    """
    import_button = amber_button("Import", ft.Icons.ADD, dropdown=True)
    new_chronicle_button = amber_button("New Chronicle", ft.Icons.ADD)

    assert import_button.bgcolor == new_chronicle_button.bgcolor
    assert import_button.padding == new_chronicle_button.padding
    assert import_button.border_radius == new_chronicle_button.border_radius
