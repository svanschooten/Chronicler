from collections.abc import Callable

import flet as ft


class Sidebar(ft.Container):
    def __init__(self, on_nav_change: Callable[[str], None], initial_view: str = "archive"):
        self.on_nav_change = on_nav_change
        self.selected_view = initial_view
        super().__init__(
            width=280,
            padding=ft.Padding.all(24),
            bgcolor=ft.Colors.BLUE_GREY_900,
        )
        self.content = self._build()

    def nav_item(self, icon: ft.IconData | str, label: str, view_id: str) -> ft.Container:
        is_selected = self.selected_view == view_id
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(
                        icon,
                        color=ft.Colors.WHITE if is_selected else ft.Colors.BLUE_GREY_400,
                        size=20,
                    ),
                    ft.Text(
                        label,
                        color=ft.Colors.WHITE if is_selected else ft.Colors.BLUE_GREY_400,
                        size=16,
                        weight=ft.FontWeight.BOLD if is_selected else None,
                    ),
                ],
                spacing=12,
            ),
            padding=ft.Padding.symmetric(vertical=10, horizontal=12),
            border_radius=8,
            bgcolor=ft.Colors.BLUE_GREY_700 if is_selected else None,
            on_click=self.handle_nav_click,
            data=view_id,
        )

    async def handle_nav_click(self, e):
        view_id = e.control.data
        self.selected_view = view_id
        self.content = self._build()
        self.update()
        await self.on_nav_change(view_id)

    def _build(self):
        return ft.Column(
            controls=[
                ft.Text(
                    "CHRONICLER",
                    size=20,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.WHITE,
                ),
                ft.Text("Preserve conversations.", size=12, color=ft.Colors.BLUE_GREY_400),
                ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
                self.nav_item(ft.Icons.SPEAKER_NOTES, "Chronicles", "archive"),
                self.nav_item(ft.Icons.PENDING_ACTIONS, "Tasks", "tasks"),
                self.nav_item(ft.Icons.SETTINGS, "Settings", "settings"),
                ft.Container(expand=True),
                ft.Divider(height=1, thickness=1, color=ft.Colors.BLACK_26),
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.FOLDER_OPEN, color=ft.Colors.BLUE_GREY_400, size=16),
                        ft.Text("Local workspace", size=12, color=ft.Colors.BLUE_GREY_400),
                    ],
                    spacing=8,
                ),
                ft.Text("v0.1.0-alpha", size=12, color=ft.Colors.BLUE_GREY_400),
            ],
            expand=True,
        )
