import flet as ft

from chronicler.core.models import Chronicle
from chronicler.core.services.transcript_service import TranscriptService


class TranscriptView(ft.Column):
    def __init__(
        self,
        chronicle: Chronicle,
        on_back,
        transcript_service: TranscriptService,
        dark_mode: bool = True,
    ):
        super().__init__(expand=True, spacing=16)
        self.chronicle = chronicle
        self.on_back = on_back
        self.transcript_service = transcript_service

        surface = ft.Colors.BLUE_GREY_700 if dark_mode else ft.Colors.WHITE
        text_color = ft.Colors.WHITE if dark_mode else ft.Colors.BROWN_900
        muted = ft.Colors.BLUE_GREY_200 if dark_mode else ft.Colors.BROWN_500
        border_color = ft.Colors.BLUE_GREY_600 if dark_mode else ft.Colors.AMBER_100

        self.transcript_area = ft.TextField(
            value="Loading transcript...",
            multiline=True,
            min_lines=12,
            max_lines=16,
            expand=True,
            border=ft.InputBorder.NONE,
            read_only=True,
        )

        self.controls = [
            ft.Row(
                controls=[
                    ft.IconButton(
                        icon=ft.Icons.ARROW_BACK,
                        icon_color=muted,
                        on_click=self.back_clicked,
                    ),
                    ft.Column(
                        expand=True,
                        controls=[
                            ft.Text(
                                self.chronicle.title,
                                size=26,
                                weight=ft.FontWeight.BOLD,
                                color=text_color,
                            ),
                            ft.Text(
                                f"{self.chronicle.kind} · "
                                f"{self.chronicle.created_at.strftime('%Y-%m-%d')} · "
                                f"{self.chronicle.duration or 'Unknown'}",
                                color=muted,
                            ),
                        ],
                    ),
                    ft.ElevatedButton(
                        content=ft.Text("Export"),
                        icon=ft.Icons.FILE_DOWNLOAD,
                        color=text_color,
                    ),
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
                                ft.Text(
                                    "Transcript",
                                    size=18,
                                    weight=ft.FontWeight.BOLD,
                                    color=text_color,
                                ),
                                self.transcript_area,
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
                                ft.Text(
                                    "Chronicle",
                                    size=18,
                                    weight=ft.FontWeight.BOLD,
                                    color=text_color,
                                ),
                                ft.Text(self.chronicle.status, color=ft.Colors.AMBER_300),
                                ft.Divider(color=border_color),
                                ft.Text("Speakers", weight=ft.FontWeight.BOLD, color=text_color),
                                ft.Text(f"{self.chronicle.speakers_count} identified", color=muted),
                                ft.Text("Tags", weight=ft.FontWeight.BOLD, color=text_color),
                                ft.Text(
                                    " · ".join([tag.name for tag in self.chronicle.tags])
                                    if self.chronicle.tags
                                    else "No tags",
                                    color=muted,
                                ),
                            ]
                        ),
                    ),
                ],
                expand=True,
            ),
        ]

    def did_mount(self):
        self.page.run_task(self.load_transcript)

    async def load_transcript(self):
        try:
            lines = await self.transcript_service.get_transcript()
            if not lines:
                self.transcript_area.value = "Transcript is empty or still processing."
            else:
                formatted_lines = []
                for line in lines:
                    formatted_lines.append(f"{line.speaker_name or 'Unknown'}: {line.text}")
                self.transcript_area.value = "\n\n".join(formatted_lines)
        except Exception as e:
            self.transcript_area.value = f"Error loading transcript: {e}"
        self.transcript_area.update()

    async def back_clicked(self, e):
        await self.on_back()
