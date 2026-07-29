import flet as ft

from models import get_chronicle
from views.chronicles import ChroniclesView
from views.settings import SettingsView
from views.sidebar import Sidebar
from views.tasks import TasksView
from views.transcript import TranscriptView


class AppShell:
    def __init__(self, page: ft.Page):
        self._page = page
        self._active_view = "chronicles"
        self._chronicles_query = ""
        self._tasks_query = ""
        self._selected_chronicle_id: str | None = None
        self._dark_mode = False
        self._hide_processed = True        

    def show(self) -> None:
        self._page.padding = 0
        self._page.theme_mode = ft.ThemeMode.DARK if self._dark_mode else ft.ThemeMode.LIGHT
        self._page.bgcolor = ft.Colors.BLUE_GREY_800 if self._dark_mode else ft.Colors.AMBER_50
        self._page.clean()
        self._page.add(
            ft.SafeArea(
                expand=True,
                content=ft.Row(
                    expand=True,
                    controls=[
                        Sidebar(self._active_view, self._navigate, self._dark_mode),
                        ft.Container(
                            expand=True,
                            padding=ft.Padding.all(28),
                            content=self._content(),
                        ),
                    ],
                ),
            )
        )

    def _navigate(self, view: str) -> None:
        self._active_view = view
        self._selected_chronicle_id = None
        self.show()

    def _set_chronicles_query(self, query: str) -> None:
        self._chronicles_query = query
        self.show()

    def _set_tasks_query(self, query: str) -> None:
        self._tasks_query = query
        self.show()

    def _open_chronicle(self, chronicle_id: str) -> None:
        self._selected_chronicle_id = chronicle_id
        self.show()

    def _set_dark_mode(self, enabled: bool) -> None:
        self._dark_mode = enabled
        self.show()

    def _set_hide_processed(self, value: bool) -> None:
        self._hide_processed = value
        self.show()

    def _content(self) -> ft.Control:
        if self._selected_chronicle_id:
            chronicle = get_chronicle(self._selected_chronicle_id)
            if chronicle:
                return TranscriptView(chronicle, self._back_to_chronicles, self._dark_mode)

        if self._active_view == "tasks":
            return TasksView(self._tasks_query, self._set_tasks_query, self._dark_mode, self._hide_processed, self._set_hide_processed)
        if self._active_view == "settings":
            return SettingsView(self._dark_mode, self._set_dark_mode)
        return ChroniclesView(self._chronicles_query, self._set_chronicles_query, self._open_chronicle, self._dark_mode)

    def _back_to_chronicles(self) -> None:
        self._selected_chronicle_id = None
        self.show()
