import logging
from collections.abc import Awaitable, Callable

import flet as ft

from chronicler.core.formatting import format_timestamp
from chronicler.core.models import Chronicle, TranscriptLine
from chronicler.core.services.task_service import TaskService
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.desktop.theme import theme_colors
from chronicler.desktop.views.transcript.export import TranscriptExporter
from chronicler.desktop.views.transcript.sources import SourcesPanel

logger = logging.getLogger(__name__)


class TranscriptView(ft.Column):
    def __init__(
        self,
        chronicle: Chronicle,
        on_back: Callable[[], Awaitable[None]],
        transcript_service: TranscriptService,
        task_service: TaskService,
        dark_mode: bool = True,
    ):
        super().__init__(expand=True, spacing=16)
        self.chronicle = chronicle
        self.on_back = on_back
        self.transcript_service = transcript_service
        self.file_picker: ft.FilePicker | None = None

        self.colors = theme_colors(dark_mode)
        self.show_timestamps = False
        self.transcript_lines: list[TranscriptLine] = []

        self.transcript_area = ft.TextField(
            value="Loading transcript...",
            multiline=True,
            min_lines=12,
            max_lines=16,
            expand=True,
            border=ft.InputBorder.NONE,
            read_only=True,
        )
        self.exporter = TranscriptExporter(
            chronicle,
            transcript_service,
            self.show_snackbar,
            lambda: self.file_picker,
        )
        self.sources = SourcesPanel(
            chronicle, transcript_service, task_service, self.colors, self.show_snackbar
        )

        self.controls = [self._header(), self._body()]

    # -- layout ---------------------------------------------------------------

    def _header(self) -> ft.Row:
        return ft.Row(
            controls=[
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK,
                    icon_color=self.colors.muted,
                    on_click=self.back_clicked,
                ),
                ft.Column(
                    expand=True,
                    controls=[
                        ft.Text(
                            self.chronicle.title,
                            size=26,
                            weight=ft.FontWeight.BOLD,
                            color=self.colors.text,
                        ),
                        ft.Text(
                            f"{self.chronicle.kind} · "
                            f"{self.chronicle.created_at.strftime('%Y-%m-%d')} · "
                            f"{self.chronicle.duration or 'Unknown'}",
                            color=self.colors.muted,
                        ),
                    ],
                ),
                self.exporter.menu(),
            ],
        )

    def _body(self) -> ft.Row:
        return ft.Row(
            controls=[self._transcript_panel(), self._detail_panel()],
            expand=True,
        )

    def _panel(self, content: ft.Control, width: int | None = None) -> ft.Container:
        return ft.Container(
            expand=width is None,
            width=width,
            bgcolor=self.colors.card,
            padding=ft.Padding.all(18),
            border=ft.Border.all(1, self.colors.border),
            border_radius=12,
            content=content,
        )

    def _transcript_panel(self) -> ft.Container:
        return self._panel(
            ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text(
                                "Transcript",
                                size=18,
                                weight=ft.FontWeight.BOLD,
                                color=self.colors.text,
                            ),
                            ft.Checkbox(
                                label="Show timestamps",
                                value=False,
                                on_change=self.show_timestamps_changed,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    self.transcript_area,
                ]
            )
        )

    def _detail_panel(self) -> ft.Container:
        tags = " · ".join([tag.name for tag in self.chronicle.tags])
        return self._panel(
            ft.Column(
                controls=[
                    ft.Text(
                        "Chronicle", size=18, weight=ft.FontWeight.BOLD, color=self.colors.text
                    ),
                    ft.Text(self.chronicle.status, color=self.colors.accent),
                    ft.Divider(color=self.colors.border),
                    ft.Text("Speakers", weight=ft.FontWeight.BOLD, color=self.colors.text),
                    ft.Text(f"{self.chronicle.speakers_count} identified", color=self.colors.muted),
                    ft.Text("Tags", weight=ft.FontWeight.BOLD, color=self.colors.text),
                    ft.Text(tags or "No tags", color=self.colors.muted),
                    ft.Divider(color=self.colors.border),
                    self.sources,
                ]
            ),
            width=220,
        )

    # -- lifecycle ------------------------------------------------------------

    def did_mount(self):
        # FilePicker is a Service, not a visual control - it belongs in
        # page.services, not page.overlay. Putting it in overlay (which expects
        # renderable widgets) makes the client choke with "Unknown control:
        # FilePicker".
        if self.file_picker is None:
            self.file_picker = ft.FilePicker()
        if self.file_picker not in self.page.services:
            self.page.services.append(self.file_picker)
            self.page.update()
        self.page.run_task(self.load_transcript)
        self.page.run_task(self.sources.load)

    def will_unmount(self):
        if self.file_picker and self.file_picker in self.page.services:
            self.page.services.remove(self.file_picker)
            self.page.update()

    def show_snackbar(self, message: str):
        self.page.show_dialog(ft.SnackBar(ft.Text(message)))

    async def back_clicked(self, e):
        await self.on_back()

    # -- transcript -----------------------------------------------------------

    async def load_transcript(self):
        try:
            self.transcript_lines = await self.transcript_service.get_transcript(
                self.chronicle.id
            )
        except Exception as e:
            self.transcript_area.value = f"Error loading transcript: {e}"
            self.transcript_area.update()
            return
        self._render_transcript()

    def _render_transcript(self):
        # Reformats already-fetched lines rather than re-querying - toggling
        # "Show timestamps" shouldn't cost a round trip or flash "Loading...".
        if not self.transcript_lines:
            self.transcript_area.value = "Transcript is empty or still processing."
        else:
            formatted_lines = []
            for line in self.transcript_lines:
                speaker = line.speaker_name or "Unknown"
                if self.show_timestamps:
                    formatted_lines.append(
                        f"[{format_timestamp(line.start_time)}] {speaker}: {line.text}"
                    )
                else:
                    formatted_lines.append(f"{speaker}: {line.text}")
            self.transcript_area.value = "\n\n".join(formatted_lines)
        self.transcript_area.update()

    async def show_timestamps_changed(self, e):
        self.show_timestamps = e.control.value
        self._render_transcript()
