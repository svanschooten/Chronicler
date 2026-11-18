"""Tests for the shared await-a-dialog-choice helpers."""

import asyncio
from unittest.mock import MagicMock

import flet as ft
import pytest

from chronicler.desktop.dialogs import Choice, ask_choice, confirm


async def _click(coro, button_index: int):
    """
    Starts `coro`, lets it reach its shown-dialog await point, clicks the button at
    `button_index`, and returns (result, page, dialog).
    """
    page = MagicMock(spec=ft.Page)
    task = asyncio.ensure_future(coro(page))
    await asyncio.sleep(0)

    page.show_dialog.assert_called_once()
    (dialog,), _ = page.show_dialog.call_args
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
            dismissed="cancel",
        )

    result, page, dialog = await _click(call, button_index=1)

    assert result == "append"
    assert dialog.actions[1].content == "Append"
    page.pop_dialog.assert_called_once()


@pytest.mark.asyncio
async def test_ask_choice_binds_each_button_to_its_own_value():
    """
    Regression guard for the loop that builds the buttons: a closure over the loop variable
    without a per-iteration binding would make every button resolve to the last choice's
    value.
    """

    async def call(page):
        return await ask_choice(
            page, "T", "M", [Choice("A", "a"), Choice("B", "b"), Choice("C", "c")], dismissed="a"
        )

    result, _, _ = await _click(call, button_index=0)

    assert result == "a"


@pytest.mark.asyncio
async def test_ask_choice_renders_only_the_primary_choice_as_filled():
    async def call(page):
        return await ask_choice(
            page,
            "T",
            "M",
            [Choice("Cancel", False), Choice("Delete", True, primary=True)],
            dismissed=False,
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


async def _dismiss(coro):
    """Starts `coro`, then closes its dialog the way Esc or a click outside does."""
    page = MagicMock(spec=ft.Page)
    task = asyncio.ensure_future(coro(page))
    await asyncio.sleep(0)
    (dialog,), _ = page.show_dialog.call_args
    dialog.on_dismiss(MagicMock())
    return await asyncio.wait_for(task, timeout=1)


@pytest.mark.asyncio
async def test_dismissing_a_choice_dialog_resolves_to_the_named_dismissed_value():
    async def call(page):
        return await ask_choice(
            page,
            "T",
            "M",
            [Choice("Append", "append"), Choice("Cancel", "cancel")],
            dismissed="cancel",
        )

    assert await _dismiss(call) == "cancel"


@pytest.mark.asyncio
async def test_dismissing_a_confirm_means_no():
    async def call(page):
        return await confirm(page, "T", "M")

    assert await _dismiss(call) is False
