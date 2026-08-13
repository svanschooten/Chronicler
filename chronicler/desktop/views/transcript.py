import asyncio
import logging
from pathlib import Path

import flet as ft

from chronicler.core.formatting import format_timestamp
from chronicler.core.models import Chronicle, TranscriptLine
from chronicler.core.services.task_service import TaskService
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.desktop.theme import theme_colors
from chronicler.desktop.widgets import amber_button

logger = logging.getLogger(__name__)


class TranscriptView(ft.Column):
    def __init__(
        self,
        chronicle: Chronicle,
        on_back,
        transcript_service: TranscriptService,
        task_service: TaskService,
        dark_mode: bool = True,
    ):
        super().__init__(expand=True, spacing=16)
        self.chronicle = chronicle
        self.on_back = on_back
        self.transcript_service = transcript_service
        self.task_service = task_service
        self.file_picker = None

        self.colors = theme_colors(dark_mode)
        surface = self.colors.card
        text_color = self.colors.text
        muted = self.colors.muted
        border_color = self.colors.border
        accent = self.colors.accent

        self.sources_list = ft.Column(spacing=4)
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
                    ft.PopupMenuButton(
                        content=amber_button("Export", ft.Icons.FILE_DOWNLOAD, dropdown=True),
                        items=[
                            ft.PopupMenuItem(
                                content=ft.Text("Plain text (.txt)"),
                                icon=ft.Icons.DESCRIPTION,
                                data=False,
                                on_click=self.export_plaintext_clicked,
                            ),
                            ft.PopupMenuItem(
                                content=ft.Text("Plain text with timestamps (.txt)"),
                                icon=ft.Icons.SCHEDULE,
                                data=True,
                                on_click=self.export_plaintext_clicked,
                            ),
                            ft.PopupMenuItem(
                                content=ft.Text("HTML (coming soon)"),
                                icon=ft.Icons.HTML,
                                disabled=True,
                            ),
                            ft.PopupMenuItem(
                                content=ft.Text("PDF (coming soon)"),
                                icon=ft.Icons.PICTURE_AS_PDF,
                                disabled=True,
                            ),
                            ft.PopupMenuItem(
                                content=ft.Text("Chronicle .zip (coming soon)"),
                                icon=ft.Icons.FOLDER_ZIP,
                                disabled=True,
                            ),
                        ],
                        tooltip="Export transcript",
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
                                ft.Row(
                                    controls=[
                                        ft.Text(
                                            "Transcript",
                                            size=18,
                                            weight=ft.FontWeight.BOLD,
                                            color=text_color,
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
                                ft.Text(self.chronicle.status, color=accent),
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
                                ft.Divider(color=border_color),
                                ft.Row(
                                    controls=[
                                        ft.Text(
                                            "Sources", weight=ft.FontWeight.BOLD, color=text_color
                                        ),
                                        ft.IconButton(
                                            icon=ft.Icons.REFRESH,
                                            icon_color=muted,
                                            icon_size=16,
                                            on_click=self.refresh_sources_clicked,
                                        ),
                                    ],
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                ),
                                self.sources_list,
                            ]
                        ),
                    ),
                ],
                expand=True,
            ),
        ]

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
        self.page.run_task(self.load_sources)

    def will_unmount(self):
        if self.file_picker and self.file_picker in self.page.services:
            self.page.services.remove(self.file_picker)
            self.page.update()

    def show_snackbar(self, message: str):
        self.page.show_dialog(ft.SnackBar(ft.Text(message)))

    async def export_plaintext_clicked(self, e):
        include_timestamps = bool(e.control.data)
        try:
            content = await self.transcript_service.export_plaintext(
                self.chronicle.id, include_timestamps=include_timestamps
            )
        except Exception as ex:
            logger.error(f"Error exporting transcript: {ex}")
            self.show_snackbar(f"Error exporting transcript: {ex}")
            return

        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in self.chronicle.title)
        suffix = "_timestamps" if include_timestamps else ""
        destination = await self.file_picker.save_file(
            dialog_title="Export transcript as plain text",
            file_name=f"{safe_title or 'transcript'}{suffix}.txt",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["txt"],
        )
        if not destination:
            return

        try:
            with open(destination, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as ex:
            logger.error(f"Error writing export file: {ex}")
            self.show_snackbar(f"Error writing export file: {ex}")
            return

        self.show_snackbar(f"Exported to {destination}")

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

    async def load_sources(self):
        try:
            sources = await self.transcript_service.list_audio_sources(self.chronicle.id)
        except Exception as e:
            logger.exception(f"Error loading audio sources: {e}")
            sources = []

        self.sources_list.controls = (
            [self.create_source_row(path) for path in sources]
            if sources
            else [ft.Text("No audio sources yet.", size=12, color=self.colors.muted)]
        )
        self.sources_list.update()

    def create_source_row(self, source_path: str) -> ft.Row:
        return ft.Row(
            controls=[
                ft.Text(
                    Path(source_path).name,
                    size=12,
                    color=self.colors.muted,
                    expand=True,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                ft.IconButton(
                    icon=ft.Icons.RECORD_VOICE_OVER,
                    icon_size=16,
                    icon_color=self.colors.muted,
                    data=source_path,
                    on_click=self.transcribe_source_clicked,
                    tooltip="Transcribe this track",
                ),
            ],
        )

    async def refresh_sources_clicked(self, e):
        await self.load_sources()

    async def _ask_speaker_name(self, source_label: str) -> str | None:
        """Same show_dialog()/pop_dialog() future pattern as ArchiveView's dialogs
        (see its _ask_overwrite_or_append for the regression note on why not to use
        the raw page.overlay approach). Existing speaker names are shown as a hint,
        not a locked-in choice: get_or_create_speaker matches by exact name, so
        typing one exactly reuses that speaker instead of creating a near-duplicate.
        """
        existing = await self.transcript_service.list_speaker_names(self.chronicle.id)
        future: asyncio.Future[str | None] = asyncio.get_event_loop().create_future()
        speaker_field = ft.TextField(
            label="Speaker name",
            autofocus=True,
            hint_text=", ".join(existing) if existing else "e.g. Alice",
        )

        def choose(result_getter):
            async def handler(e):
                if not future.done():
                    future.set_result(result_getter())
                self.page.pop_dialog()

            return handler

        dialog = ft.AlertDialog(
            title=ft.Text(f"Transcribe '{source_label}'"),
            content=ft.Column(
                [
                    ft.Text(
                        "Which speaker is this track? This audio source is assumed "
                        "to be a single speaker - transcribing it replaces only that "
                        "speaker's existing lines, not the whole transcript."
                    ),
                    speaker_field,
                ],
                tight=True,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=choose(lambda: None)),
                ft.FilledButton("Transcribe", on_click=choose(lambda: speaker_field.value)),
            ],
        )
        self.page.show_dialog(dialog)
        return await future

    async def transcribe_source_clicked(self, e):
        source_path = e.control.data
        label = Path(source_path).name
        speaker_name = await self._ask_speaker_name(label)
        if not speaker_name:
            return

        await self.task_service.queue_transcribe(self.chronicle.id, source_path, speaker_name)
        self.show_snackbar(f"Queued transcription of '{label}' as {speaker_name}")

    async def back_clicked(self, e):
        await self.on_back()
