from collections.abc import Callable

import flet as ft

from models import CHRONICLES, Chronicle


def ChroniclesView(
    query: str,
    on_query_change: Callable[[str], None],
    on_open: Callable[[str], None],
    dark_mode: bool,
) -> ft.Column:
    background = ft.Colors.BLUE_GREY_800 if dark_mode else ft.Colors.AMBER_50
    surface = ft.Colors.BLUE_GREY_700 if dark_mode else ft.Colors.WHITE
    text_color = ft.Colors.WHITE if dark_mode else ft.Colors.BROWN_900
    muted = ft.Colors.BLUE_GREY_200 if dark_mode else ft.Colors.BROWN_500
    border_color = ft.Colors.BLUE_GREY_600 if dark_mode else ft.Colors.AMBER_100

    def chronicle_card(item: Chronicle) -> ft.Container:
        tags = " · ".join(item.tags)
        return ft.Container(
            bgcolor=surface,
            padding=ft.Padding.all(18),
            border=ft.Border.all(1, border_color),
            border_radius=12,     
            on_click=lambda _: on_open(item.chronicle_id),
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text(item.kind.upper(), size=12, weight=ft.FontWeight.BOLD, color=muted),
                            ft.Text(item.status, size=12, color=muted),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Text(item.title, size=18, weight=ft.FontWeight.BOLD, color=text_color),
                    ft.Text(item.preview, max_lines=2, color=muted),
                    ft.Row(
                        controls=[
                            ft.Text(item.date, color=muted),
                            ft.Text(item.duration, color=muted),
                            ft.Text(f"{item.speakers} speakers", color=muted),
                        ],
                        wrap=True,
                    ),
                    ft.Text(tags, color=muted),
                ],
            ),
        )

    return ft.Column(
        expand=True,
        controls=[
            ft.Row(
                controls=[
                    ft.Column(
                        controls=[
                            ft.Text("Chronicles", size=30, weight=ft.FontWeight.BOLD, color=text_color),
                            ft.Text("Your self-contained conversation projects.", color=muted),
                        ],
                    ),
                    ft.Button(content="Import recording", icon=ft.Icons.ADD, bgcolor=ft.Colors.AMBER_700, color=ft.Colors.BROWN_900),
                    ft.Button(content="Import transcript", icon=ft.Icons.ADD, bgcolor=ft.Colors.AMBER_700, color=ft.Colors.BROWN_900),
                    ft.Button(content="Import chronicle", icon=ft.Icons.ADD, bgcolor=ft.Colors.AMBER_700, color=ft.Colors.BROWN_900),
                ],
                wrap=True,
            ),
            ft.Row(
                controls=[
                    ft.Icon(ft.Icons.SEARCH, color=muted),
                    ft.TextField(
                        expand=True,
                        value=query,
                        hint_text="Search chronicles",
                        on_change=lambda event: on_query_change(event.data),
                    ),
                ],
            ),
            ft.Container(
                bgcolor=background,
                padding=ft.Padding.only(top=6),
                content=ft.Column(
                    controls=[chronicle_card(chronicle) for chronicle in CHRONICLES],
                    spacing=12, 
                    auto_scroll=True, 
                ),
            ),
        ],
        spacing=16,
    )
