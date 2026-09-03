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
from chronicler.desktop.operations import ChronicleOperations
from chronicler.desktop.picking import FilePickerFlow
from chronicler.desktop.reveal import RevealError, open_in_file_manager
from chronicler.desktop.theme import theme_colors
from chronicler.desktop.views.transcript.actions import (
    ChronicleActionCallbacks,
    ChronicleActions,
)
from chronicler.desktop.views.transcript.editor import TranscriptEditor
from chronicler.desktop.views.transcript.export import TranscriptExporter
from chronicler.desktop.views.transcript.recording import RecordingDialog
from chronicler.desktop.views.transcript.sources import SourcesPanel
from chronicler.desktop.views.transcript.summaries import SummariesPanel
from chronicler.i18n import t

logger = logging.getLogger(__name__)


def t_bold(value: str, color: str) -> ft.Text:
    return ft.Text(value, weight=ft.FontWeight.BOLD, color=color)


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
        model_error: Callable[[], str | None] | None = None,
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
        self.editing = False
        self.transcript_lines: list[TranscriptLine] = []

        self.transcript_area = ft.TextField(
            value=t("transcript.loading"),
            multiline=True,
            min_lines=12,
            max_lines=16,
            expand=True,
            border=ft.InputBorder.NONE,
            read_only=True,
        )
        self.editor = TranscriptEditor(
            chronicle,
            transcript_service,
            self.colors,
            self.show_snackbar,
            self.reload,
        )
        self.edit_toggle = ft.IconButton(
            icon=ft.Icons.EDIT,
            icon_color=self.colors.muted,
            tooltip=t("transcript.edit"),
            on_click=self.edit_toggled,
        )
        self.transcript_body = ft.Container(expand=True, content=self.transcript_area)
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
            model_error,
        )
        self.operations = ChronicleOperations(
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
            self.show_snackbar,
            lambda: self.page,
            on_changed=self.reload,
        )
        self.actions = ChronicleActions(
            chronicle,
            self.operations,
            self.colors,
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
        self.timestamps_checkbox = ft.Checkbox(
            label=t("transcript.show_timestamps"),
            value=False,
            on_change=self.show_timestamps_changed,
        )
        return self._panel(
            ft.Column(
                expand=True,
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text(
                                t("transcript.title"),
                                size=18,
                                weight=ft.FontWeight.BOLD,
                                color=self.colors.text,
                            ),
                            ft.Row(
                                tight=True,
                                controls=[self.timestamps_checkbox, self.edit_toggle],
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    self.transcript_body,
                ],
            )
        )

    async def edit_toggled(self, e) -> None:
        """
        Reading and editing are separate modes on purpose: the read view is one selectable
        block, which is what makes it readable, and that is exactly what cannot be edited
        line by line. See docs/transcript-editing.md.
        """
        self.editing = not self.editing
        self.edit_toggle.icon = ft.Icons.DONE if self.editing else ft.Icons.EDIT
        self.edit_toggle.tooltip = t("transcript.done") if self.editing else t("transcript.edit")
        self.timestamps_checkbox.disabled = self.editing
        self.transcript_body.content = self.editor if self.editing else self.transcript_area

        _repaint(self.edit_toggle, self.timestamps_checkbox, self.transcript_body)

        if self.editing:
            await self.editor.load()
        else:
            await self.load_transcript()

    def _detail_panel(self) -> ft.Container:
        tags = " · ".join([tag.name for tag in self.chronicle.tags])
        return self._panel(
            ft.Column(
                controls=[
                    ft.Text(
                        t("transcript.chronicle"),
                        size=18,
                        weight=ft.FontWeight.BOLD,
                        color=self.colors.text,
                    ),
                    ft.Text(self.chronicle.status, color=self.colors.accent),
                    ft.Divider(color=self.colors.border),
                    t_bold(t("transcript.speakers"), self.colors.text),
                    ft.Text(
                        t("transcript.speakers_identified", count=self.chronicle.speakers_count),
                        color=self.colors.muted,
                    ),
                    t_bold(t("transcript.tags"), self.colors.text),
                    ft.Text(tags or t("archive.no_tags"), color=self.colors.muted),
                    ft.Divider(color=self.colors.border),
                    ft.Row(
                        controls=[
                            ft.TextButton(
                                t("sources.record"),
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
        if self.editing:
            await self.load_transcript()
            return
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
            self.transcript_area.value = t("transcript.error", error=e)
            self.transcript_area.update()
            return
        self._render_transcript()

    def _render_transcript(self):
        if not self.transcript_lines:
            self.transcript_area.value = t("transcript.empty")
        else:
            formatted_lines = []
            for line in self.transcript_lines:
                speaker = line.speaker_name or t("common.unknown")
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


def _repaint(*controls: ft.Control) -> None:
    for control in controls:
        try:
            control.update()
        except (RuntimeError, AssertionError):
            pass
