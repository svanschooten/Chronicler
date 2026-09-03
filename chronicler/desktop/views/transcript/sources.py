"""The transcript view's Sources panel - a chronicle's audio tracks and the actions on them."""

import logging
from collections.abc import Callable

import flet as ft

from chronicler.core.models import AudioSource, Chronicle, SourceState
from chronicler.core.services.task_service import TaskService
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.desktop.dialogs import await_dialog
from chronicler.desktop.theme import ThemeColors
from chronicler.i18n import t

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
        self.sources: dict[str, AudioSource] = {}

        self.source_list = ft.Column(spacing=4)
        super().__init__(
            tight=True,
            controls=[
                ft.Row(
                    controls=[
                        ft.Text(t("sources.title"), weight=ft.FontWeight.BOLD, color=colors.text),
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
        except Exception as error:
            logger.exception(f"Error loading audio sources: {error}")
            sources = []

        self.sources = {source.filename: source for source in sources}
        self.source_list.controls = (
            [self._source_row(source) for source in sources]
            if sources
            else [ft.Text(t("sources.empty"), size=12, color=self.colors.muted)]
        )
        self.source_list.update()

    async def refresh_clicked(self, e):
        await self.load()

    def _status_line(self, source: AudioSource) -> str:
        parts = [source.speaker_name or t("sources.no_speaker")]
        if source.missing:
            parts.append(t("sources.missing"))
        if source.is_transcribed:
            parts.append(t("sources.transcribed"))
        elif source.transcription_state == SourceState.FAILED:
            parts.append(source.transcription_error or t("sources.failed"))
        elif source.transcription_state == SourceState.RUNNING:
            parts.append(t("sources.transcribing"))
        if source.is_normalized:
            parts.append(t("sources.normalized"))
        return " · ".join(parts)

    def _source_row(self, source: AudioSource) -> ft.Row:
        return ft.Row(
            controls=[
                ft.Column(
                    expand=True,
                    spacing=0,
                    controls=[
                        ft.Text(
                            source.filename,
                            size=12,
                            color=self.colors.text,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Text(self._status_line(source), size=10, color=self.colors.muted),
                    ],
                ),
                *(
                    []
                    if source.is_normalized or source.missing
                    else [
                        ft.IconButton(
                            icon=ft.Icons.GRAPHIC_EQ,
                            icon_size=16,
                            icon_color=self.colors.muted,
                            data=source.filename,
                            on_click=self.normalize_source_clicked,
                            tooltip=t("sources.normalize"),
                        )
                    ]
                ),
                ft.IconButton(
                    icon=ft.Icons.PERSON,
                    icon_size=16,
                    icon_color=self.colors.muted,
                    data=source.filename,
                    on_click=self.assign_speaker_clicked,
                    tooltip=t("sources.assign_speaker"),
                ),
                ft.IconButton(
                    icon=ft.Icons.RECORD_VOICE_OVER,
                    icon_size=16,
                    icon_color=self.colors.muted,
                    data=source.filename,
                    on_click=self.transcribe_source_clicked,
                    tooltip=t("sources.transcribe"),
                ),
            ],
        )

    def _path_of(self, filename: str) -> str:
        """The server-side path of a source, as reported when it was listed."""
        source = self.sources.get(filename)
        return source.path if source and source.path else filename

    async def normalize_source_clicked(self, e):
        filename = e.control.data
        source = self.sources.get(filename)
        if source is not None and source.missing:
            self.show_snackbar(t("sources.missing_cannot_transcribe", name=filename))
            return

        await self.task_service.queue_normalize(self.chronicle.id, self._path_of(filename))
        self.show_snackbar(t("tasks.queued_normalize", name=filename))
        await self.load()

    async def assign_speaker_clicked(self, e):
        filename = e.control.data
        source = self.sources.get(filename)
        chosen = await self._ask_speaker(filename, source.speaker_name if source else None)
        if not chosen:
            return
        await self.transcript_service.assign_speaker(self.chronicle.id, filename, chosen)
        await self.load()

    async def transcribe_source_clicked(self, e):
        filename = e.control.data
        source = self.sources.get(filename)

        if source is not None and source.missing:
            self.show_snackbar(t("sources.missing_cannot_transcribe", name=filename))
            return

        speaker = source.speaker_name if source else None
        if not speaker:
            speaker = await self._ask_speaker(filename, None)
            if not speaker:
                return
            await self.transcript_service.assign_speaker(self.chronicle.id, filename, speaker)

        await self.task_service.queue_transcribe(
            self.chronicle.id, self._path_of(filename), speaker
        )
        self.show_snackbar(t("tasks.queued_transcribe", name=filename, speaker=speaker))
        await self.load()

    async def _ask_speaker(self, source_label: str, current: str | None) -> str | None:
        """Offers the speakers already known to this chronicle, or a newly typed name."""
        existing = await self.transcript_service.speaker_suggestions(self.chronicle.id)

        dropdown = ft.Dropdown(
            label=t("sources.speaker"),
            value=current if current in existing else None,
            options=[ft.DropdownOption(key=name, text=name) for name in existing],
            enable_filter=True,
            editable=True,
        )
        new_name = ft.TextField(label=t("sources.new_speaker"), autofocus=not existing)

        def build(on_choice) -> ft.AlertDialog:
            return ft.AlertDialog(
                title=ft.Text(t("sources.ask_speaker_title", name=source_label)),
                content=ft.Column(
                    [ft.Text(t("sources.ask_speaker_message")), dropdown, new_name], tight=True
                ),
                actions=[
                    ft.TextButton(t("common.cancel"), on_click=on_choice(lambda: None)),
                    ft.FilledButton(
                        t("sources.transcribe_action"),
                        on_click=on_choice(
                            lambda: (new_name.value or dropdown.value or "").strip()
                        ),
                    ),
                ],
            )

        chosen = await await_dialog(self.page, build)
        return chosen or None
