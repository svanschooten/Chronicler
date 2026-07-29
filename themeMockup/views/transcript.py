from collections.abc import Callable

import flet as ft

from models import Chronicle


def TranscriptView(item: Chronicle, on_back: Callable[[], None], dark_mode: bool) -> ft.Column:
    surface = ft.Colors.BLUE_GREY_700 if dark_mode else ft.Colors.WHITE
    text_color = ft.Colors.WHITE if dark_mode else ft.Colors.BROWN_900
    muted = ft.Colors.BLUE_GREY_200 if dark_mode else ft.Colors.BROWN_500
    border_color = ft.Colors.BLUE_GREY_600 if dark_mode else ft.Colors.AMBER_100

    transcript = (
        "Welcome, everyone. Before we get into the roadmap, I want to close the loop on the customer interviews from last week.\n\n"
        "The clearest request was better visibility into what happens after a recording is imported. A persistent task timeline would make the processing stages easier to trust.\n\n"
        "Let’s make that the focus for the next sprint, alongside the revised export flow."
    )

    return ft.Column(
        expand=True,
        controls=[
            ft.Row(
                controls=[
                    ft.IconButton(icon=ft.Icons.ARROW_BACK, icon_color=muted, on_click=lambda _: on_back()),
                    ft.Column(
                        expand=True,
                        controls=[
                            ft.Text(item.title, size=26, weight=ft.FontWeight.BOLD, color=text_color),
                            ft.Text(f"{item.kind} · {item.date} · {item.duration}", color=muted),
                        ],
                    ),
                    ft.Button(content="Export", icon=ft.Icons.FILE_DOWNLOAD, color=text_color),
                ],
            ),
            ft.Row(
                controls=[
                    ft.Container(
                        expand=True,
                        bgcolor=surface,
                        padding=ft.Padding.all(18),
                        border=ft.Border.all(1, border_color),
                        border_radius=12,
                        content=ft.Column(
                            controls=[
                                ft.Text("Transcript", size=18, weight=ft.FontWeight.BOLD, color=text_color),
                                ft.TextField(value=transcript, multiline=True, min_lines=12, max_lines=16, expand=True),
                            ]
                        ),
                    ),
                    ft.Container(
                        width=220,
                        bgcolor=surface,
                        padding=ft.Padding.all(18),
                        border=ft.Border.all(1, border_color),
                        border_radius=12,
                        content=ft.Column(
                            controls=[
                                ft.Text("Chronicle", size=18, weight=ft.FontWeight.BOLD, color=text_color),
                                ft.Text(item.status, color=ft.Colors.AMBER_300),
                                ft.Divider(color=border_color),
                                ft.Text("Speakers", weight=ft.FontWeight.BOLD, color=text_color),
                                ft.Text(f"{item.speakers} identified", color=muted),
                                ft.Text("Tags", weight=ft.FontWeight.BOLD, color=text_color),
                                ft.Text(" · ".join(item.tags), color=muted),
                            ]
                        ),
                    ),
                ],
                expand=True,
            ),
        ],
        spacing=16,
    )
