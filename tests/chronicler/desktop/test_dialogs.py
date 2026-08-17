"""Tests for the shared await-a-dialog-choice helpers.

These exercise the real show_dialog()/pop_dialog() mechanism rather than the views
that use it. The regression they guard against: an earlier version removed the dialog
from page.overlay immediately after setting `open = False`, which drops AlertDialog's
close animation and its post-animation dismiss callback. The buttons still "worked"
(the future resolved and the caller proceeded) but the dialog never visually closed -
so a test that only checks the resolved value would have passed throughout.
"""

import asyncio
from unittest.mock import MagicMock

import flet as ft
import pytest

from chronicler.desktop.dialogs import Choice, ask_choice, ask_text, confirm


async def _click(coro, button_index: int, before_click=None):
    """Starts `coro`, lets it reach its shown-dialog await point, clicks the button at
    `button_index`, and returns (result, page, dialog)."""
    page = MagicMock(spec=ft.Page)
    task = asyncio.ensure_future(coro(page))
    await asyncio.sleep(0)

    page.show_dialog.assert_called_once()
    (dialog,), _ = page.show_dialog.call_args
    if before_click is not None:
        before_click(dialog)
    await dialog.actions[button_index].on_click(MagicMock())

    return await asyncio.wait_for(task, timeout=1), page, dialog


@pytest.mark.asyncio
async def test_ask_choice_resolves_to_the_clicked_choices_value():
    async def call(page):
        return await ask_choice(
            page,
            "Transcript already exists",
            "Overwrite or append?",
            [
                Choice("Cancel", "cancel"),
                Choice("Append", "append"),
                Choice("Overwrite", "overwrite", primary=True),
            ],
        )

    result, page, dialog = await _click(call, button_index=1)

    assert result == "append"
    assert dialog.actions[1].content == "Append"
    page.pop_dialog.assert_called_once()


@pytest.mark.asyncio
async def test_ask_choice_binds_each_button_to_its_own_value():
    """Regression guard for the loop that builds the buttons: a closure over the loop
    variable without a per-iteration binding would make every button resolve to the
    last choice's value."""

    async def call(page):
        return await ask_choice(
            page, "T", "M", [Choice("A", "a"), Choice("B", "b"), Choice("C", "c")]
        )

    result, _, _ = await _click(call, button_index=0)

    assert result == "a"


@pytest.mark.asyncio
async def test_ask_choice_renders_only_the_primary_choice_as_filled():
    async def call(page):
        return await ask_choice(
            page, "T", "M", [Choice("Cancel", False), Choice("Delete", True, primary=True)]
        )

    _, _, dialog = await _click(call, button_index=1)

    assert isinstance(dialog.actions[0], ft.TextButton)
    assert isinstance(dialog.actions[1], ft.FilledButton)


@pytest.mark.asyncio
async def test_confirm_resolves_true_on_the_confirm_button():
    async def call(page):
        return await confirm(page, "Delete chronicle?", "Are you sure?")

    result, page, dialog = await _click(call, button_index=1)

    assert result is True
    assert dialog.actions[1].content == "Delete"
    page.pop_dialog.assert_called_once()


@pytest.mark.asyncio
async def test_confirm_resolves_false_on_cancel():
    async def call(page):
        return await confirm(page, "Delete chronicle?", "Are you sure?")

    result, _, _ = await _click(call, button_index=0)

    assert result is False


@pytest.mark.asyncio
async def test_confirm_uses_a_custom_confirm_label():
    async def call(page):
        return await confirm(page, "T", "M", confirm_label="Discard")

    _, _, dialog = await _click(call, button_index=1)

    assert dialog.actions[1].content == "Discard"


@pytest.mark.asyncio
async def test_ask_text_resolves_to_the_fields_value_at_click_time():
    """The value getter has to be lazy: the user types *after* the dialog is built, so
    a button bound to `field.value` as read at build time would always resolve to the
    field's initial contents."""
    field = ft.TextField(label="Speaker name")

    async def call(page):
        return await ask_text(page, "Transcribe", "Which speaker?", field, "Transcribe")

    def type_into_field(_dialog):
        field.value = "Bob"

    result, page, dialog = await _click(call, button_index=1, before_click=type_into_field)

    assert result == "Bob"
    assert dialog.actions[1].content == "Transcribe"
    page.pop_dialog.assert_called_once()


@pytest.mark.asyncio
async def test_ask_text_resolves_to_none_on_cancel():
    field = ft.TextField(value="typed but abandoned")

    async def call(page):
        return await ask_text(page, "T", "M", field)

    result, _, _ = await _click(call, button_index=0)

    assert result is None
