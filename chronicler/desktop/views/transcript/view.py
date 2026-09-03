import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

import flet as ft

from chronicler.core.config import Settings, get_settings
from chronicler.core.formatting import format_timestamp
from chronicler.core.models import Chronicle, TranscriptLine
from chronicler.core.services.task_service import TaskService
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.desktop.dialogs import await_dialog
from chronicler.desktop.extras_prompt import ExtraInstaller
from chronicler.desktop.imports import ImportCoordinator
from chronicler.desktop.picking import FilePickerFlow
from chronicler.desktop.reveal import RevealError, open_in_file_manager
from chronicler.desktop.theme import theme_colors
from chronicler.desktop.views.transcript.actions import (
    ChronicleActionCallbacks,
    ChronicleActions,
)
from chronicler.desktop.views.transcript.export import TranscriptExporter
from chronicler.desktop.views.transcript.recording import RecordingDialog
from chronicler.desktop.views.transcript.sources import SourcesPanel
from chronicler.desktop.views.transcript.summaries import SummariesPanel
from chronicler.i18n import t

logger = logging.getLogger(__name__)

MIN_DETAIL_WIDTH = 260
MAX_DETAIL_WIDTH = 520
DETAIL_WIDTH_SHARE = 0.24


def detail_panel_width(page_width: float | None) -> float:
    """
    How wide the chronicle panel should be for a window of `page_width`.

    A share of the window rather than a fixed 260px, so long filenames and speaker names
    are readable on a big screen - clamped at both ends so a narrow window still leaves
    room for the transcript and an ultrawide one does not strand the panel. See
    docs/desktop.md.
    """
    try:
        width = float(page_width)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return MIN_DETAIL_WIDTH
    return min(max(width * DETAIL_WIDTH_SHARE, MIN_DETAIL_WIDTH), MAX_DETAIL_WIDTH)


class TranscriptView(ft.Column):
    def __init__(
        self,
        chronicle: Chronicle,
        on_back: Callable[[], Awaitable[None]],
        transcript_service: TranscriptService,
        task_service: TaskService,
        dark_mode: bool = True,
        chronicle_service=None,
        file_stager=None,
        available_models=None,
        capabilities: Callable[[], set[str]] | None = None,
        settings: Settings | None = None,
        on_reload: Callable[[], Awaitable[None]] | None = None,
    ):
        super().__init__(expand=True, spacing=16)
        self.chronicle = chronicle
        self.on_back = on_back
        self.transcript_service = transcript_service
        self.task_service = task_service
        self.chronicle_service = chronicle_service
        self.file_stager = file_stager
        self.settings = settings or get_settings()
        self.capabilities = capabilities
        self.on_reload = on_reload
        self.file_picker: ft.FilePicker | None = None
        self.picker = FilePickerFlow(lambda: self.file_picker, self.show_snackbar)

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
            chronicle,
            transcript_service,
            task_service,
            self.colors,
            self.show_snackbar,
            self.settings,
        )
        self.summaries = SummariesPanel(
            chronicle,
            transcript_service,
            task_service,
            self.colors,
            self.show_snackbar,
            available_models,
            self._can_summarize,
        )
        self.actions = ChronicleActions(
            chronicle,
            ImportCoordinator(
                chronicle_service,
                task_service,
                transcript_service,
                file_stager.stage if file_stager is not None else _no_stager,
            ),
            task_service,
            transcript_service,
            chronicle_service,
            self.picker,
            self.colors,
            self.show_snackbar,
            ChronicleActionCallbacks(
                on_changed=self.reload,
                on_deleted=self.back_to_archive,
                on_summarize=self.summaries.generate,
            ),
            self._can_summarize,
        )
        self.detail_panel = self._detail_panel()

        self.controls = [self._header(), self.actions, self._body()]

    def _can_summarize(self) -> bool:
        """
        Unknown capabilities means "assume it works": the button explaining itself is
        better than one that refuses because a handshake has not landed yet.
        """
        return self.capabilities is None or "summarize" in self.capabilities()

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
                ft.IconButton(
                    icon=ft.Icons.MENU_BOOK,
                    icon_color=self.colors.muted,
                    tooltip=t("summaries.read_transcript"),
                    on_click=self.read_transcript_clicked,
                ),
                ft.IconButton(
                    icon=ft.Icons.FOLDER_OPEN,
                    icon_color=self.colors.muted,
                    tooltip=t("summaries.open_folder"),
                    on_click=self.open_folder_clicked,
                ),
                self.exporter.menu(),
            ],
        )

    def _body(self) -> ft.Row:
        return ft.Row(
            controls=[self._transcript_panel(), self.detail_panel],
            expand=True,
        )

    def _panel(self, content: ft.Control, width: float | None = None) -> ft.Container:
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
                    ft.Row(
                        controls=[
                            ft.TextButton(
                                t("summaries.record"),
                                icon=ft.Icons.MIC,
                                on_click=self.record_clicked,
                            )
                        ]
                    ),
                    self.sources,
                    ft.Divider(color=self.colors.border),
                    self.summaries,
                ],
                scroll=ft.ScrollMode.AUTO,
            ),
            width=MIN_DETAIL_WIDTH,
        )

    def did_mount(self):
        if self.file_picker is None:
            self.file_picker = ft.FilePicker()
        if self.file_picker not in self.page.services:
            self.page.services.append(self.file_picker)
            self.page.update()
        for form in self.actions.forms:
            form.attach(self.page)
        self.page.on_resize = self.page_resized
        self.page_resized(None)
        self.page.run_task(self.load_transcript)
        self.page.run_task(self.sources.load)
        self.page.run_task(self.summaries.load)

    def will_unmount(self):
        for form in self.actions.forms:
            form.detach(self.page)
        if self.page.on_resize is self.page_resized:
            self.page.on_resize = None
        if self.file_picker and self.file_picker in self.page.services:
            self.page.services.remove(self.file_picker)
            self.page.update()

    def page_resized(self, _event) -> None:
        self.detail_panel.width = detail_panel_width(getattr(self.page, "width", None))
        try:
            self.detail_panel.update()
        except (RuntimeError, AssertionError):
            pass

    async def reload(self) -> None:
        """Rebuilds the whole view after something changed the chronicle."""
        if self.on_reload is not None:
            await self.on_reload()
            return
        await self.load_transcript()
        await self.sources.load()
        await self.summaries.load()

    async def back_to_archive(self) -> None:
        await self.on_back()

    def show_snackbar(self, message: str):
        self.page.show_dialog(ft.SnackBar(ft.Text(message)))

    async def back_clicked(self, e):
        await self.on_back()

    async def open_folder_clicked(self, e):
        try:
            directory = await self.transcript_service.chronicle_directory(self.chronicle.id)
            open_in_file_manager(Path(directory))
        except (RevealError, OSError) as error:
            self.show_snackbar(t("summaries.folder_failed", error=error))

    async def read_transcript_clicked(self, e):
        try:
            text = await self.transcript_service.read_transcript_text(
                self.chronicle.id, include_timestamps=self.show_timestamps
            )
        except Exception as error:
            self.show_snackbar(t("transcript.error", error=error))
            return

        def build(on_choice) -> ft.AlertDialog:
            return ft.AlertDialog(
                title=ft.Text(self.chronicle.title),
                content=ft.Container(
                    width=760,
                    height=520,
                    content=ft.Column(
                        scroll=ft.ScrollMode.AUTO,
                        controls=[
                            ft.Text(
                                text or t("transcript.empty"),
                                selectable=True,
                                font_family="monospace",
                                size=12,
                                color=self.colors.text,
                            )
                        ],
                    ),
                ),
                actions=[ft.TextButton(t("common.close"), on_click=on_choice(lambda: None))],
            )

        await await_dialog(self.page, build)

    async def record_clicked(self, e):
        if self.chronicle_service is None or self.file_stager is None:
            self.show_snackbar(t("recording.unavailable"))
            return

        dialog = RecordingDialog(
            self.chronicle,
            self.chronicle_service,
            self.file_stager,
            self.show_snackbar,
            self.colors,
            ExtraInstaller(self.settings, self.show_snackbar, self.colors),
        )
        await dialog.run(self.page)
        await self.sources.load()

    async def load_transcript(self):
        try:
            self.transcript_lines = await self.transcript_service.get_transcript(self.chronicle.id)
        except Exception as e:
            self.transcript_area.value = f"Error loading transcript: {e}"
            self.transcript_area.update()
            return
        self._render_transcript()

    def _render_transcript(self):
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


async def _no_stager(path: str) -> str:
    """Staging is unavailable, so an import can only report why - see docs/desktop.md."""
    raise RuntimeError("File staging is not available in this view")
