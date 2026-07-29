from collections.abc import Callable

import flet as ft


def Sidebar(active: str, on_navigate: Callable[[str], None], dark_mode: bool) -> ft.Container:
    surface = ft.Colors.BLUE_GREY_900 if dark_mode else ft.Colors.BROWN_50
    text_color = ft.Colors.WHITE if dark_mode else ft.Colors.BROWN_900
    muted = ft.Colors.BLUE_GREY_300 if dark_mode else ft.Colors.BROWN_500
    selected = ft.Colors.BLUE_GREY_700 if dark_mode else ft.Colors.AMBER_100

    def nav_button(label: str, icon: object, key: str) -> ft.Button:
        is_active = active == key
        return ft.Button(
            content=label,
            icon=icon,
            color=text_color if is_active else muted,
            bgcolor=selected if is_active else None,
            on_click=lambda _: on_navigate(key),
        )

    return ft.Container(
        width=220,
        bgcolor=surface,
        padding=ft.Padding.all(18),
        content=ft.Column(
            expand=True,
            controls=[
                ft.Text("CHRONICLER", size=18, weight=ft.FontWeight.BOLD, color=text_color),
                ft.Text("Preserve conversations.", color=muted),
                ft.Divider(color=muted),
                nav_button("Chronicles", ft.Icons.SPEAKER_NOTES, "chronicles"),
                nav_button("Tasks", ft.Icons.PENDING_ACTIONS, "tasks"),
                nav_button("Settings", ft.Icons.SETTINGS, "settings"),
                ft.Container(expand=True),
                ft.Divider(color=muted),
                ft.Row(
                    controls=[
                        ft.IconButton(icon=ft.Icons.FOLDER_OPEN, icon_color=muted),
                        ft.Text("Local workspace", color=muted),
                    ]
                ),
            ],
        ),
    )
