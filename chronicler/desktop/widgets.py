import flet as ft

AMBER_BUTTON_PADDING = ft.Padding(left=16, top=8, right=16, bottom=8)


def amber_button(
    label: str,
    icon: ft.IconData,
    on_click=None,
    dropdown: bool = False,
) -> ft.Container:
    """A single styling source for every amber action button (New Chronicle, Import,
    Export, ...) so they render identically instead of each call site hand-rolling
    its own Container/Row and drifting apart. `dropdown=True` appends a small
    separator + chevron, signaling the button opens a menu rather than acting
    directly - only set it when this is wrapped in a PopupMenuButton.
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
