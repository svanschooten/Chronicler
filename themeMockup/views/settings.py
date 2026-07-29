from collections.abc import Callable

import flet as ft


def SettingsView(dark_mode: bool, on_theme_change: Callable[[bool], None]) -> ft.Column:
    surface = ft.Colors.BLUE_GREY_700 if dark_mode else ft.Colors.WHITE
    text_color = ft.Colors.WHITE if dark_mode else ft.Colors.BROWN_900
    muted = ft.Colors.BLUE_GREY_200 if dark_mode else ft.Colors.BROWN_500
    border_color = ft.Colors.BLUE_GREY_600 if dark_mode else ft.Colors.AMBER_100

    def setting_card(title: str, description: str, content: object) -> ft.Container:
        return ft.Container(
            bgcolor=surface,
            padding=ft.Padding.all(18),
            border=ft.Border.all(1, border_color),
            border_radius=12,
            content=ft.Row(
                controls=[
                    ft.Column(
                        expand=True,
                        controls=[
                            ft.Text(title, weight=ft.FontWeight.BOLD, color=text_color),
                            ft.Text(description, color=muted),
                        ],
                    ),
                    content,
                ],
            ),
        )

    return ft.Column(
        expand=True,
        controls=[
            ft.Text("Settings", size=30, weight=ft.FontWeight.BOLD, color=text_color),
            ft.Text("Preferences for this machine and workspace.", color=muted),
            ft.Text("Appearance", size=18, weight=ft.FontWeight.BOLD, color=text_color),
            setting_card(
                "Dark workspace",
                "Use a low-light interface while reviewing long transcripts.",
                ft.Switch(value=dark_mode, on_change=lambda event: on_theme_change(event.data == "true")),
            ),
            ft.Text("Workspace", size=18, weight=ft.FontWeight.BOLD, color=text_color),
            setting_card(
                "Local workspace",
                "~/Documents/Chronicler Workspace",
                ft.IconButton(icon=ft.Icons.FOLDER_OPEN, icon_color=muted),
            ),
            ft.Text("Connection", size=18, weight=ft.FontWeight.BOLD, color=text_color),
            setting_card(
                "Service layer",
                "Local desktop services are ready to connect.",
                ft.Text("Local", weight=ft.FontWeight.BOLD, color=ft.Colors.AMBER_300),
            ),
        ],
        spacing=16,
    )
