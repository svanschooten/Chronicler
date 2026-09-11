"""
Editing a transcript one line at a time.

Whole-blob editing was the obvious alternative and is worse: parsing the text back into
lines would have to guess where speaker turns and timings belong, and a single
mis-parsed line would silently rewrite the ones around it. One control per line means an
edit touches exactly the line it was typed into. See docs/transcript-editing.md.
"""

import logging
from collections.abc import Awaitable, Callable

import flet as ft

from chronicler.core.formatting import format_timestamp
from chronicler.core.models import Chronicle, TranscriptLine
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.desktop.dialogs import confirm
from chronicler.desktop.theme import ThemeColors
from chronicler.desktop.widgets import chosen_value, searchable_dropdown
from chronicler.i18n import t

logger = logging.getLogger(__name__)

CONFIRMATION_EXCERPT = 60


class TranscriptEditor(ft.Column):
    def __init__(
        self,
        chronicle: Chronicle,
        transcript_service: TranscriptService,
        colors: ThemeColors,
        show_snackbar: Callable[[str], None],
        on_changed: Callable[[], Awaitable[None]],
    ):
        self.chronicle = chronicle
        self.transcript_service = transcript_service
        self.colors = colors
        self.show_snackbar = show_snackbar
        self.on_changed = on_changed

        self.lines: dict[str, TranscriptLine] = {}
        self.line_list = ft.ListView(spacing=6, expand=True)
        super().__init__(expand=True, controls=[self.line_list])

    async def load(self) -> None:
        try:
            lines = await self.transcript_service.get_transcript(self.chronicle.id)
            speakers = await self.transcript_service.speaker_suggestions(self.chronicle.id)
        except Exception as error:
            logger.exception("Could not load the transcript for editing")
            self._show_message(t("transcript.error", error=error))
            return

        self.lines = {str(line.id): line for line in lines}
        if not lines:
            self._show_message(t("transcript.empty"))
            return

        self.line_list.controls = [self._row(line, speakers) for line in lines]
        self._refresh()

    def _show_message(self, message: str) -> None:
        self.line_list.controls = [ft.Text(message, size=12, color=self.colors.muted)]
        self._refresh()

    def _refresh(self) -> None:
        try:
            self.line_list.update()
        except (RuntimeError, AssertionError):
            pass

    def _row(self, line: TranscriptLine, speakers: list[str]) -> ft.Row:
        """
        Each control carries `<field>:<line id>` so a handler knows which line it is for
        without the row having to be found again.
        """
        key = str(line.id)
        return ft.Row(
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                ft.Text(
                    format_timestamp(line.start_time),
                    size=11,
                    width=72,
                    color=self.colors.muted,
                    font_family="monospace",
                ),
                searchable_dropdown(
                    speakers,
                    value=line.speaker_name,
                    width=150,
                    data=f"speaker:{key}",
                    on_select=self.speaker_changed,
                ),
                ft.TextField(
                    data=f"text:{key}",
                    value=line.text,
                    expand=True,
                    multiline=True,
                    min_lines=1,
                    max_lines=6,
                    on_blur=self.text_blurred,
                ),
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    icon_size=16,
                    icon_color=self.colors.muted,
                    data=f"delete:{key}",
                    tooltip=t("transcript.delete_line"),
                    on_click=self.delete_clicked,
                ),
            ],
        )

    @staticmethod
    def _line_id(control: ft.Control) -> str:
        return str(control.data).split(":", 1)[1]

    def _line_for(self, control: ft.Control) -> TranscriptLine | None:
        return self.lines.get(self._line_id(control))

    async def text_blurred(self, e) -> None:
        """A blur fires whether or not anything was typed, so unchanged text is ignored."""
        control = e.control
        line = self._line_for(control)
        if line is None:
            return

        typed = control.value or ""
        if typed == line.text:
            return

        if not await self._save(line, text=typed):
            control.value = line.text
            self._repaint(control)
            return
        line.text = typed

    async def speaker_changed(self, e) -> None:
        control = e.control
        line = self._line_for(control)
        if line is None:
            return

        chosen = chosen_value(control)
        if not chosen or chosen == line.speaker_name:
            return

        if not await self._save(line, speaker_name=chosen):
            control.value = line.speaker_name
            self._repaint(control)
            return
        line.speaker_name = chosen

    async def _save(self, line: TranscriptLine, **changes) -> bool:
        try:
            await self.transcript_service.update_line(self.chronicle.id, line.id, **changes)
        except Exception as error:
            logger.exception("Could not save a transcript line")
            self.show_snackbar(t("transcript.save_failed", error=error))
            return False
        return True

    async def delete_clicked(self, e) -> None:
        line = self._line_for(e.control)
        if line is None:
            return

        excerpt = line.text[:CONFIRMATION_EXCERPT]
        if len(line.text) > CONFIRMATION_EXCERPT:
            excerpt += "..."

        if not await confirm(
            self.page,
            t("transcript.delete_line_title"),
            t("transcript.delete_line_message", excerpt=excerpt),
            confirm_label=t("common.delete"),
        ):
            return

        try:
            await self.transcript_service.delete_line(self.chronicle.id, line.id)
        except Exception as error:
            logger.exception("Could not delete a transcript line")
            self.show_snackbar(t("transcript.save_failed", error=error))
            return

        await self.load()
        await self.on_changed()

    @staticmethod
    def _repaint(control: ft.Control) -> None:
        try:
            control.update()
        except (RuntimeError, AssertionError):
            pass
