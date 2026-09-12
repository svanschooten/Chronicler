"""The transcript view's Sources panel - a chronicle's audio tracks and the actions on them."""

import logging
from collections.abc import Callable

import flet as ft

from chronicler.core.config import Settings, get_settings
from chronicler.core.models import AudioSource, Chronicle, SourceState
from chronicler.core.services.task_service import TaskService
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.desktop.theme import ThemeColors
from chronicler.desktop.views.transcript.transcribe_dialog import (
    TranscribeChoice,
    TranscribeDialog,
)
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
        settings: Settings | None = None,
        capabilities: Callable[[], set[str]] | None = None,
    ):
        self.chronicle = chronicle
        self.transcript_service = transcript_service
        self.task_service = task_service
        self.colors = colors
        self.show_snackbar = show_snackbar
        self.settings = settings or get_settings()
        self.capabilities = capabilities
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
                    tooltip=source.filename,
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
                        self._source_action(
                            ft.Icons.GRAPHIC_EQ,
                            source.filename,
                            self.normalize_source_clicked,
                            t("sources.normalize"),
                            enabled=self.can("normalize"),
                            disabled_tooltip=t("sources.normalize_unavailable"),
                        )
                    ]
                ),
                self._source_action(
                    ft.Icons.RECORD_VOICE_OVER,
                    source.filename,
                    self.transcribe_source_clicked,
                    t("transcribe.start_again") if source.is_transcribed else t("transcribe.start"),
                    enabled=self.can("transcribe"),
                    disabled_tooltip=t("sources.transcribe_unavailable"),
                ),
            ],
        )

    def can(self, capability: str) -> bool:
        """
        Whether the service layer offers `capability`.

        Unknown means "assume it works" - a handshake that has not landed yet should not
        grey out half the panel. Both answers are the server's in thin-client mode; it is
        its extras that decide, not this machine's. See docs/deployment-and-rpc.md.
        """
        return self.capabilities is None or capability in self.capabilities()

    def _source_action(
        self,
        icon: ft.IconData,
        filename: str,
        on_click,
        tooltip: str,
        enabled: bool,
        disabled_tooltip: str,
    ) -> ft.IconButton:
        """A disabled button still shows a tooltip, which is what lets it explain itself."""
        return ft.IconButton(
            icon=icon,
            icon_size=16,
            icon_color=self.colors.muted if enabled else self.colors.border,
            data=filename,
            on_click=on_click,
            tooltip=tooltip if enabled else disabled_tooltip,
            disabled=not enabled,
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

    async def transcribe_source_clicked(self, e):
        filename = e.control.data
        source = self.sources.get(filename)

        if source is None or source.missing:
            self.show_snackbar(t("sources.missing_cannot_transcribe", name=filename))
            return

        choice = await self._ask_transcribe(source)
        if choice is None:
            return

        await self.transcript_service.assign_speaker(self.chronicle.id, filename, choice.speaker)
        if not choice.transcribe:
            self.show_snackbar(t("sources.speaker_saved", speaker=choice.speaker))
            await self.load()
            return

        await self.task_service.queue_transcribe(
            self.chronicle.id,
            self._path_of(filename),
            choice.speaker,
            language=choice.language,
            model_size=choice.model_size,
            no_speech_threshold=choice.no_speech_threshold,
            normalize_first=choice.normalize_first,
        )
        self.show_snackbar(t("tasks.queued_transcribe", name=filename, speaker=choice.speaker))
        await self.load()

    async def _ask_transcribe(self, source: AudioSource) -> TranscribeChoice | None:
        """Every speaker the workspace knows, not just this chronicle's - see docs/speakers.md."""
        speakers = await self.transcript_service.speaker_suggestions(self.chronicle.id)
        return await TranscribeDialog(source, speakers, self.settings).ask(self.page)
