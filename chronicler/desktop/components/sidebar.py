from collections.abc import Awaitable, Callable

import flet as ft

from chronicler import __version__
from chronicler.desktop.theme import theme_colors
from chronicler.i18n import t


class Sidebar(ft.Container):
    def __init__(
        self,
        on_nav_change: Callable[[str], Awaitable[None]],
        initial_view: str = "archive",
        dark_mode: bool = True,
    ):
        self.on_nav_change = on_nav_change
        self.selected_view = initial_view
        self.colors = theme_colors(dark_mode)
        super().__init__(
            width=280,
            padding=ft.Padding.all(24),
            bgcolor=self.colors.sidebar,
        )
        self.content = self._build()

    def nav_item(self, icon: ft.IconData, label: str, view_id: str) -> ft.Container:
        is_selected = self.selected_view == view_id
        item_color = self.colors.text if is_selected else self.colors.muted
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(icon, color=item_color, size=20),
                    ft.Text(
                        label,
                        color=item_color,
                        size=16,
                        weight=ft.FontWeight.BOLD if is_selected else None,
                    ),
                ],
                spacing=12,
            ),
            padding=ft.Padding.symmetric(vertical=10, horizontal=12),
            border_radius=8,
            bgcolor=self.colors.card if is_selected else None,
            on_click=self.handle_nav_click,
            data=view_id,
        )

    async def handle_nav_click(self, e):
        view_id = e.control.data
        self.selected_view = view_id
        self.content = self._build()
        self.update()
        await self.on_nav_change(view_id)

    def set_dark_mode(self, dark_mode: bool):
        """
        Colors are baked into the built controls (same pattern every other view uses) -
        called from DesktopApp.on_dark_mode_change since, unlike the content views, the
        sidebar is built once in main() and never naturally rebuilt on navigation.
        """
        self.colors = theme_colors(dark_mode)
        self.bgcolor = self.colors.sidebar
        self.content = self._build()
        self.update()

    def relabel(self):
        """Rebuilds after a locale change, since labels are baked in at build time."""
        self.content = self._build()
        self.update()

    def _build(self):
        return ft.Column(
            controls=[
                ft.Text(
                    t("app.name").upper(),
                    size=20,
                    weight=ft.FontWeight.BOLD,
                    color=self.colors.text,
                ),
                ft.Text(t("app.tagline"), size=12, color=self.colors.muted),
                ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
                self.nav_item(ft.Icons.SPEAKER_NOTES, t("nav.archive"), "archive"),
                self.nav_item(ft.Icons.PENDING_ACTIONS, t("nav.tasks"), "tasks"),
                self.nav_item(ft.Icons.SETTINGS, t("nav.settings"), "settings"),
                ft.Container(expand=True),
                ft.Divider(height=1, thickness=1, color=self.colors.border),
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.FOLDER_OPEN, color=self.colors.muted, size=16),
                        ft.Text(t("settings.workspace.local"), size=12, color=self.colors.muted),
                    ],
                    spacing=8,
                ),
                ft.Text(f"v{__version__}", size=12, color=self.colors.muted),
            ],
            expand=True,
        )
