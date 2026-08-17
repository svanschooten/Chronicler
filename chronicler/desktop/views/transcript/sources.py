"""The transcript view's Sources panel - a chronicle's imported audio tracks, and
the action that queues one of them for transcription.

Its own control rather than part of the view because it has independent state (the
list of files on disk) that it reloads on its own, and because assigning a speaker to
a track is a distinct interaction from reading a transcript.
"""

import logging
from collections.abc import Callable
from pathlib import Path

import flet as ft

from chronicler.core.models import Chronicle
from chronicler.core.services.task_service import TaskService
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.desktop.dialogs import ask_text
from chronicler.desktop.theme import ThemeColors

logger = logging.getLogger(__name__)


class SourcesPanel(ft.Column):
    def __init__(
        self,
        chronicle: Chronicle,
        transcript_service: TranscriptService,
        task_service: TaskService,
        colors: ThemeColors,
        show_snackbar: Callable[[str], None],
    ):
        self.chronicle = chronicle
        self.transcript_service = transcript_service
        self.task_service = task_service
        self.colors = colors
        self.show_snackbar = show_snackbar

        self.source_list = ft.Column(spacing=4)
        super().__init__(
            tight=True,
            controls=[
                ft.Row(
                    controls=[
                        ft.Text("Sources", weight=ft.FontWeight.BOLD, color=colors.text),
                        ft.IconButton(
                            icon=ft.Icons.REFRESH,
                            icon_color=colors.muted,
                            icon_size=16,
                            on_click=self.refresh_clicked,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                self.source_list,
            ],
        )

    async def load(self):
        try:
            sources = await self.transcript_service.list_audio_sources(self.chronicle.id)
        except Exception as e:
            logger.exception(f"Error loading audio sources: {e}")
            sources = []

        self.source_list.controls = (
            [self._source_row(path) for path in sources]
            if sources
            else [ft.Text("No audio sources yet.", size=12, color=self.colors.muted)]
        )
        self.source_list.update()

    async def refresh_clicked(self, e):
        await self.load()

    def _source_row(self, source_path: str) -> ft.Row:
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

    async def transcribe_source_clicked(self, e):
        source_path = e.control.data
        label = Path(source_path).name
        speaker_name = await self._ask_speaker_name(label)
        if not speaker_name:
            return

        await self.task_service.queue_transcribe(self.chronicle.id, source_path, speaker_name)
        self.show_snackbar(f"Queued transcription of '{label}' as {speaker_name}")

    async def _ask_speaker_name(self, source_label: str) -> str | None:
        """Existing speaker names are offered as a hint, not a locked-in choice:
        get_or_create_speaker matches by exact name, so typing one exactly reuses that
        speaker instead of creating a near-duplicate."""
        existing = await self.transcript_service.list_speaker_names(self.chronicle.id)
        return await ask_text(
            self.page,
            f"Transcribe '{source_label}'",
            "Which speaker is this track? This audio source is assumed to be a "
            "single speaker - transcribing it replaces only that speaker's existing "
            "lines, not the whole transcript.",
            ft.TextField(
                label="Speaker name",
                autofocus=True,
                hint_text=", ".join(existing) if existing else "e.g. Alice",
            ),
            confirm_label="Transcribe",
        )
