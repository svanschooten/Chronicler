import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

import flet as ft

from chronicler.core import extras
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


READER_INSET = ft.Padding(left=40, top=24, right=40, bottom=24)
READER_MARGIN_X = 140
READER_MARGIN_Y = 200
READER_MIN_WIDTH = 480
READER_MIN_HEIGHT = 320
DEFAULT_PAGE_WIDTH = 1200
DEFAULT_PAGE_HEIGHT = 800

TRANSCRIPT_LINE_HEIGHT = 1.35
TRANSCRIPT_TEXT_SIZE = 13
TRANSCRIPT_STYLE = ft.TextStyle(height=TRANSCRIPT_LINE_HEIGHT, size=TRANSCRIPT_TEXT_SIZE)

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

        self.transcript_text = ft.Text(
            t("transcript.loading"),
            selectable=True,
            color=self.colors.text,
            style=TRANSCRIPT_STYLE,
        )
        self.transcript_area = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            controls=[self.transcript_text],
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
            capabilities,
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
            lambda: self.settings.llm.model,
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

    def _record_button(self) -> ft.TextButton:
        """
        Recording runs on this machine whatever the deployment mode, so this asks the
        local extras rather than the service layer's capabilities.

        Enabled when the extra is there, and also when it is merely missing from a source
        checkout - that is one prompt away. A packaged build without it cannot be fixed
        from here, so the button says so instead of opening a dialog that ends in an
        error. See docs/optional-extras.md.
        """
        usable = extras.is_usable("recording")
        return ft.TextButton(
            t("sources.record"),
            icon=ft.Icons.MIC,
            on_click=self.record_clicked,
            disabled=not usable,
            tooltip=None if usable else t("sources.record_unavailable"),
        )

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
                    ft.Row(controls=[self._record_button()]),
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
        """
        Focused reading: the whole transcript, sized to the window rather than to a
        fixed 760x520 that left most of a large monitor unused.
        """
        try:
            text = await self.transcript_service.read_transcript_text(
                self.chronicle.id, include_timestamps=self.show_timestamps
            )
        except Exception as error:
            self.show_snackbar(t("transcript.error", error=error))
            return

        reader = ft.Container(
            content=ft.Column(
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    ft.Text(
                        text or t("transcript.empty"),
                        selectable=True,
                        font_family="monospace",
                        style=TRANSCRIPT_STYLE,
                        color=self.colors.text,
                    )
                ],
            )
        )
        self._size_reader(reader)

        fullscreen_button = ft.IconButton(
            icon=ft.Icons.FULLSCREEN,
            icon_color=self.colors.muted,
            tooltip=t("transcript.fullscreen"),
            visible=self._can_go_fullscreen(),
        )

        async def toggle_fullscreen(_event):
            window = self.page.window
            window.full_screen = not window.full_screen
            fullscreen_button.icon = (
                ft.Icons.FULLSCREEN_EXIT if window.full_screen else ft.Icons.FULLSCREEN
            )
            fullscreen_button.tooltip = (
                t("transcript.fullscreen_exit")
                if window.full_screen
                else t("transcript.fullscreen")
            )
            self._size_reader(reader)
            self.page.update()

        fullscreen_button.on_click = toggle_fullscreen

        def build(on_choice) -> ft.AlertDialog:
            return ft.AlertDialog(
                inset_padding=READER_INSET,
                title=ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Text(self.chronicle.title, overflow=ft.TextOverflow.ELLIPSIS),
                        fullscreen_button,
                    ],
                ),
                content=reader,
                actions=[ft.TextButton(t("common.close"), on_click=on_choice(lambda: None))],
            )

        await await_dialog(self.page, build)

    def _can_go_fullscreen(self) -> bool:
        """
        A browser tab has no window to resize - `page.window` is inert there, so the
        button would do nothing visible. The web client is the one mode that hits this.
        """
        return not getattr(self.page, "web", False)

    def _size_reader(self, reader: ft.Container) -> None:
        """
        The reader fills the window it is in, minus room for the dialog's own chrome.

        Fixed at 760x520 it was a small island on a large monitor - which is the opposite
        of what a focused reading mode is for.
        """
        reader.width = max(
            (self.page.width or DEFAULT_PAGE_WIDTH) - READER_MARGIN_X, READER_MIN_WIDTH
        )
        reader.height = max(
            (self.page.height or DEFAULT_PAGE_HEIGHT) - READER_MARGIN_Y, READER_MIN_HEIGHT
        )

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
            self.transcript_text.value = t("transcript.error", error=e)
            _repaint(self.transcript_text, self.transcript_area)
            return
        self._render_transcript()

    def _render_transcript(self):
        """
        One selectable block, one line per turn.

        The blank line between turns and the sixteen-line cap both came from rendering
        this as a read-only TextField: it stopped partway down the panel however much
        room there was, and cut off anything past the cap. A scrolling Text fills the
        panel at any window size, and the spacing is a line height rather than an empty
        line. See docs/transcript-editing.md.
        """
        self.transcript_text.value = self._transcript_body()
        _repaint(self.transcript_text, self.transcript_area)

    def _transcript_body(self) -> str:
        if not self.transcript_lines:
            return t("transcript.empty")

        formatted_lines = []
        for line in self.transcript_lines:
            speaker = line.speaker_name or t("common.unknown")
            if self.show_timestamps:
                formatted_lines.append(
                    f"[{format_timestamp(line.start_time)}] {speaker}: {line.text}"
                )
            else:
                formatted_lines.append(f"{speaker}: {line.text}")
        return "\n".join(formatted_lines)

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
