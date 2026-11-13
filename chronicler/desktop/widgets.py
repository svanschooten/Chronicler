import flet as ft

AMBER_BUTTON_PADDING = ft.Padding(left=16, top=8, right=16, bottom=8)


def amber_button(
    label: str,
    icon: ft.IconData,
    on_click=None,
    dropdown: bool = False,
) -> ft.Container:
    """
    A single styling source for every amber action button (New Chronicle, Import, Export,
    ...) so they render identically instead of each call site hand-rolling its own
    Container/Row and drifting apart.
    """
    row_controls: list[ft.Control] = [
        ft.Icon(icon, color=ft.Colors.BROWN_900),
        ft.Text(label, color=ft.Colors.BROWN_900, weight=ft.FontWeight.BOLD),
    ]
    if dropdown:
        row_controls += [
            ft.Container(width=1, height=16, bgcolor=ft.Colors.BROWN_900, opacity=0.4),
            ft.Icon(ft.Icons.EXPAND_MORE, color=ft.Colors.BROWN_900, size=18),
        ]

    return ft.Container(
        content=ft.Row(row_controls, alignment=ft.MainAxisAlignment.CENTER, spacing=8),
        bgcolor=ft.Colors.AMBER_700,
        padding=AMBER_BUTTON_PADDING,
        border_radius=8,
        on_click=on_click,
        ink=True,
    )


MENU_HEIGHT = 280


def searchable_dropdown(
    options: list[str],
    value: str | None = None,
    label: str | None = None,
    width: int | None = None,
    data: str | None = None,
    on_select=None,
) -> ft.Dropdown:
    """
    A dropdown for a list nobody wants to scroll: models, speakers, anything open-ended.

    Two things make one usable that a plain `ft.Dropdown` does not do on its own.

    `menu_height` is the important one. Without it the menu grows to fit every option, so
    a provider offering seventy models produces a menu taller than the window - covering
    the text field you would have typed a filter into, which leaves no way to narrow the
    list at all. Capped, the menu scrolls and the field stays visible.

    Emptying the field on focus is the other. It arrives holding the current selection, so
    typing inserts into the middle of that ("venice/llama-3b" + "qwen") and matches
    nothing. Clearing is done through `value`, not `text`: in Flet 0.86 `text` is reported
    by the client and writing it back changes nothing on screen, while `value` is the
    selection and does repaint the field. Leaving without choosing puts the selection back.

    See docs/desktop.md.
    """
    remembered = value

    def clear_for_typing(event):
        nonlocal remembered
        remembered = event.control.value
        event.control.value = None
        _repaint(event.control)

    def restore_if_nothing_chosen(event):
        if event.control.value is None and not (event.control.text or "").strip():
            event.control.value = remembered
            _repaint(event.control)

    return ft.Dropdown(
        label=label,
        width=width,
        data=data,
        value=value,
        options=[ft.DropdownOption(key=option, text=option) for option in options],
        editable=True,
        enable_filter=True,
        menu_height=MENU_HEIGHT,
        on_select=on_select,
        on_focus=clear_for_typing,
        on_blur=restore_if_nothing_chosen,
    )


def chosen_value(control: ft.Control) -> str:
    """
    What the user actually settled on, typed or picked.

    An editable Dropdown keeps the two apart: `text` tracks the field, `value` holds the
    option last *selected*. Reading `value` alone silently ignores a name typed over it,
    which is how a transcription could run as the wrong speaker. Reading `text` alone is
    no better: it is empty both before the client has reported anything and while the
    field is cleared for filtering, so an untouched field would read as blank.

    Typed text wins when there is any; otherwise the selection does. A plain TextField has
    `value` alone and no such split.
    """
    typed = (getattr(control, "text", None) or "").strip()
    if typed:
        return typed
    return (getattr(control, "value", None) or "").strip()


def _repaint(control: ft.Control) -> None:
    try:
        control.update()
    except (RuntimeError, AssertionError):
        pass
