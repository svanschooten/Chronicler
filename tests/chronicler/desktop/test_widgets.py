from unittest.mock import MagicMock

import flet as ft

from chronicler.desktop.widgets import (
    MENU_HEIGHT,
    amber_button,
    chosen_value,
    searchable_dropdown,
)


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


MODELS = [f"provider/model-{n}" for n in range(70)]


class TestSearchableDropdown:
    def test_the_menu_is_capped_so_it_cannot_swallow_the_window(self):
        """
        Uncapped, seventy options produce a menu taller than the window - covering the
        text field you would have typed a filter into, so the list cannot be narrowed.
        """
        dropdown = searchable_dropdown(MODELS)

        assert dropdown.menu_height == MENU_HEIGHT

    def test_it_can_be_typed_into_and_filters(self):
        dropdown = searchable_dropdown(MODELS)

        assert dropdown.editable is True
        assert dropdown.enable_filter is True

    def test_every_option_is_still_offered(self):
        dropdown = searchable_dropdown(MODELS, value="provider/model-3")

        assert len(dropdown.options) == 70
        assert dropdown.value == "provider/model-3"

    def test_focus_empties_the_field_so_typing_filters_from_scratch(self):
        """
        Otherwise "model-4" lands in the middle of "provider/model-3" and matches nothing.
        Clearing goes through `value`: writing `text` does not repaint the field.
        """
        dropdown = searchable_dropdown(MODELS, value="provider/model-3")

        dropdown.on_focus(MagicMock(control=dropdown))

        assert dropdown.value is None

    def test_leaving_without_choosing_puts_the_selection_back(self):
        dropdown = searchable_dropdown(MODELS, value="provider/model-3")
        dropdown.on_focus(MagicMock(control=dropdown))

        dropdown.on_blur(MagicMock(control=dropdown))

        assert dropdown.value == "provider/model-3"

    def test_leaving_with_something_typed_keeps_the_typing(self):
        dropdown = searchable_dropdown(MODELS, value="provider/model-3")
        dropdown.on_focus(MagicMock(control=dropdown))
        dropdown.text = "someone new"

        dropdown.on_blur(MagicMock(control=dropdown))

        assert dropdown.value is None
        assert chosen_value(dropdown) == "someone new"

    def test_a_chosen_option_survives_a_later_focus(self):
        dropdown = searchable_dropdown(MODELS, value="provider/model-3")
        dropdown.on_focus(MagicMock(control=dropdown))
        dropdown.value = "provider/model-9"  # as the client reports a selection

        dropdown.on_focus(MagicMock(control=dropdown))
        dropdown.on_blur(MagicMock(control=dropdown))

        assert dropdown.value == "provider/model-9"


class TestChosenValue:
    def test_what_was_typed_wins_over_what_was_selected(self):
        """Reading `value` alone silently uses the option the user typed over."""
        dropdown = searchable_dropdown(MODELS, value="provider/model-3")
        dropdown.text = "provider/model-9"

        assert chosen_value(dropdown) == "provider/model-9"

    def test_an_untouched_field_reports_its_selection(self):
        dropdown = searchable_dropdown(MODELS, value="provider/model-3")

        assert dropdown.text is None
        assert chosen_value(dropdown) == "provider/model-3"

    def test_a_field_cleared_for_filtering_still_reports_its_selection(self):
        """The clear is how filtering starts, so it must not read as "nothing chosen"."""
        dropdown = searchable_dropdown(MODELS, value="provider/model-3")
        dropdown.text = ""

        assert chosen_value(dropdown) == "provider/model-3"

    def test_a_plain_text_field_has_only_its_value(self):
        assert chosen_value(ft.TextField(value="  Alice  ")) == "Alice"

    def test_an_empty_control_is_an_empty_string(self):
        assert chosen_value(ft.TextField()) == ""
