"""Await-a-dialog-choice helpers shared by every desktop view.

Flet has no built-in primitive for "show a modal and await what the user picked",
so `_await_dialog` below is the standard workaround: a Future that the action
buttons resolve, mirroring how `ft.FilePicker.pick_files` itself is implemented
under the hood.

It goes through `page.show_dialog()`/`page.pop_dialog()` rather than manually
appending to `page.overlay` and toggling `open` - `AlertDialog`'s close is animated
client-side, and `show_dialog()` wraps `on_dismiss` so the dialog is only actually
removed once the client confirms the animation finished (see
`BasePage._wrap_dialog_on_dismiss`'s own comment: removing it earlier "can drop the
post-animation dismiss callback entirely"). An earlier version of this code called
`page.overlay.remove(dialog)` immediately after `open = False`, which did exactly
that - the buttons worked (the future resolved, the import proceeded) but the dialog
visually never closed.
"""

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

import flet as ft

T = TypeVar("T")


@dataclass(frozen=True)
class Choice(Generic[T]):
    """One action button on a choice dialog. `primary` renders it as a FilledButton
    rather than a TextButton - use it for the action the dialog is really asking
    about, not for Cancel."""

    label: str
    value: T
    primary: bool = False


async def _await_dialog(
    page: ft.Page,
    dialog_factory: Callable[[Callable[[Callable[[], T]], Any]], ft.AlertDialog],
) -> T:
    """Shows the dialog built by `dialog_factory` and resolves to whatever the
    clicked button asked for.

    `dialog_factory` receives an `on_choice` builder: call it with a zero-argument
    getter and it returns a Flet click handler that resolves this dialog's future to
    that getter's return value. The getter is deliberately lazy rather than a plain
    value so a button can resolve to something only known at click time - the current
    contents of a TextField, say (see `ask_text`).
    """
    future: asyncio.Future[T] = asyncio.get_event_loop().create_future()

    def on_choice(value_getter: Callable[[], T]) -> Any:
        async def handler(e):
            if not future.done():
                future.set_result(value_getter())
            page.pop_dialog()

        return handler

    page.show_dialog(dialog_factory(on_choice))
    return await future


async def ask_choice(
    page: ft.Page,
    title: str,
    message: str,
    choices: Sequence[Choice[T]],
) -> T:
    """A modal question with one button per choice, resolving to the chosen value."""

    def build(on_choice) -> ft.AlertDialog:
        return ft.AlertDialog(
            title=ft.Text(title),
            content=ft.Text(message),
            actions=[
                (ft.FilledButton if choice.primary else ft.TextButton)(
                    choice.label,
                    on_click=on_choice(lambda choice=choice: choice.value),  # type: ignore[misc]
                )
                for choice in choices
            ],
        )

    return await _await_dialog(page, build)


async def confirm(page: ft.Page, title: str, message: str, confirm_label: str = "Delete") -> bool:
    """The yes/no case of `ask_choice`. Cancel is the non-primary button, so a
    destructive confirmation never renders Cancel as the emphasized action."""
    return await ask_choice(
        page,
        title,
        message,
        [Choice("Cancel", False), Choice(confirm_label, True, primary=True)],
    )


async def ask_text(
    page: ft.Page,
    title: str,
    message: str,
    field: ft.TextField,
    confirm_label: str = "OK",
) -> str | None:
    """A modal that collects free text, resolving to the field's contents - or None
    if the user cancelled. `field` is passed in rather than built here so the caller
    controls its label, hint and initial value."""

    def build(on_choice) -> ft.AlertDialog:
        return ft.AlertDialog(
            title=ft.Text(title),
            content=ft.Column([ft.Text(message), field], tight=True),
            actions=[
                ft.TextButton("Cancel", on_click=on_choice(lambda: None)),
                ft.FilledButton(confirm_label, on_click=on_choice(lambda: field.value)),
            ],
        )

    return await _await_dialog(page, build)
