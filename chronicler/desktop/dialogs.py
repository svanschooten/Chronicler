"""Await-a-dialog-choice helpers shared by every desktop view."""

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

import flet as ft

T = TypeVar("T")


@dataclass(frozen=True)
class Choice(Generic[T]):
    """One action button on a choice dialog."""

    label: str
    value: T
    primary: bool = False


async def await_dialog(
    page: ft.Page,
    dialog_factory: Callable[[Callable[[Callable[[], T]], Any]], ft.AlertDialog],
) -> T:
    """
    Shows the dialog built by `dialog_factory` and resolves to whatever the clicked button
    asked for.
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

    return await await_dialog(page, build)


async def confirm(page: ft.Page, title: str, message: str, confirm_label: str = "Delete") -> bool:
    """The yes/no case of `ask_choice`."""
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
    """
    A modal that collects free text, resolving to the field's contents - or None if the user
    cancelled.
    """

    def build(on_choice) -> ft.AlertDialog:
        return ft.AlertDialog(
            title=ft.Text(title),
            content=ft.Column([ft.Text(message), field], tight=True),
            actions=[
                ft.TextButton("Cancel", on_click=on_choice(lambda: None)),
                ft.FilledButton(confirm_label, on_click=on_choice(lambda: field.value)),
            ],
        )

    return await await_dialog(page, build)
