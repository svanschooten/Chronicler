"""
Editing a transcript one line at a time.

Whole-blob editing was the obvious alternative and is worse: parsing the text back into
lines would have to guess where speaker turns and timings belong, and a single
mis-parsed line would silently rewrite the ones around it. One control per line means an
edit touches exactly the line it was typed into. See docs/transcript-editing.md.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import flet as ft

from chronicler.core.database_manager import NewerSchemaError
from chronicler.core.formatting import format_timestamp, looks_synthetic
from chronicler.core.models import Chronicle, TranscriptLine
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.desktop.dialogs import confirm
from chronicler.desktop.theme import ThemeColors
from chronicler.desktop.widgets import chosen_value, searchable_dropdown
from chronicler.i18n import format_count, t

logger = logging.getLogger(__name__)

CONFIRMATION_EXCERPT = 60
WINDOW_SIZE = 100


def describe_transcript_error(error: BaseException) -> str:
    """What to show when a chronicle's transcript cannot be loaded, in the user's language."""
    if isinstance(error, NewerSchemaError):
        return t("transcript.newer_version")
    return t("transcript.error", error=error)


class LinePager(ft.Row):
    """First / previous / "Lines 101-200 of 1,686" / next / last, for the editor's window."""

    def __init__(self, colors: ThemeColors, on_page: Callable[..., Awaitable[None]]):
        # Not `on_click`: on a Row that name reads as the Row's own event.
        self.on_page = on_page
        self.first_button = self._button(ft.Icons.FIRST_PAGE, "transcript.first_lines")
        self.previous_button = self._button(ft.Icons.CHEVRON_LEFT, "transcript.previous_lines")
        self.next_button = self._button(ft.Icons.CHEVRON_RIGHT, "transcript.next_lines")
        self.last_button = self._button(ft.Icons.LAST_PAGE, "transcript.last_lines")
        self.label = ft.Text(size=12, color=colors.muted)
        super().__init__(
            visible=False,
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[
                self.first_button,
                self.previous_button,
                self.label,
                self.next_button,
                self.last_button,
            ],
        )

    def _button(self, icon: ft.IconData, tooltip_key: str) -> ft.IconButton:
        return ft.IconButton(
            icon=icon,
            icon_size=18,
            tooltip=t(tooltip_key),
            on_click=self.on_page,
            data=tooltip_key,
        )

    def show(self, start: int, shown: list[TranscriptLine], total: int, timed: bool) -> None:
        """
        Only a transcript longer than one window gets a pager.

        The label gives the window's time span as well as its line numbers when the
        timings are real: the reader shows times, not line numbers, so a time is what
        someone coming from the reader knows the passage by.
        """
        self.visible = total > WINDOW_SIZE
        counts = {
            "first": format_count(start + 1),
            "last": format_count(start + len(shown)),
            "total": format_count(total),
        }
        if timed and shown:
            self.label.value = t(
                "transcript.line_window_timed",
                **counts,
                start=format_timestamp(shown[0].start_time),
                end=format_timestamp(shown[-1].end_time),
            )
        else:
            self.label.value = t("transcript.line_window", **counts)
        self.first_button.disabled = self.previous_button.disabled = start == 0
        self.next_button.disabled = self.last_button.disabled = start + WINDOW_SIZE >= total


@dataclass
class _Saves:
    """
    The saves still running for one field of one line, and the value the database is
    known to hold: what the last save to succeed wrote, or what the line held before
    the first of them started.
    """

    confirmed: str | None
    pending: int = 0


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
        # Keyed by (field, line id). See `_start_save`.
        self._saves: dict[tuple[str, str], _Saves] = {}
        self.ordered: list[TranscriptLine] = []
        self.speakers: list[str] = []
        self.window_start = 0
        # False when the timings are line indices, which say nothing as a time span.
        self.timed = False

        self.line_list = ft.ListView(spacing=6, expand=True)
        # The same pager twice: above the list, and as the list's last item, so the end
        # of a window leads straight on to the next without scrolling back up.
        self.pager = LinePager(colors, self.pager_clicked)
        self.bottom_pager = LinePager(colors, self.pager_clicked)
        super().__init__(expand=True, controls=[self.pager, self.line_list])

    async def load(self, show_line: uuid.UUID | None = None) -> None:
        """
        Loads the lines and shows the window that was showing, so deleting a line on the
        fifth window does not throw the user back to the first.

        `show_line` opens a window that starts at that line instead: the view passes the
        first match of the reader's find, so editing goes straight to what was found. The
        window starts at the line rather than at its usual boundary because a ListView
        cannot be scrolled to one of its rows, so the top is the one place it is sure to
        be seen.
        """
        try:
            lines = await self.transcript_service.get_transcript(self.chronicle.id)
            speakers = await self.transcript_service.speaker_suggestions(self.chronicle.id)
        except Exception as error:
            logger.exception("Could not load the transcript for editing")
            self._show_message(describe_transcript_error(error))
            return

        self.lines = {str(line.id): line for line in lines}
        self.ordered = list(lines)
        self.timed = not looks_synthetic(self.ordered)
        self.speakers = list(speakers)
        if not lines:
            self._show_message(t("transcript.empty"))
            return

        start = self.window_start
        if show_line is not None:
            start = next((i for i, line in enumerate(self.ordered) if line.id == show_line), start)
        await self._show_window(start)

    async def pager_clicked(self, e) -> None:
        last = self._last_window_start()
        target = {
            "transcript.first_lines": 0,
            "transcript.previous_lines": self.window_start - WINDOW_SIZE,
            "transcript.next_lines": self.window_start + WINDOW_SIZE,
            "transcript.last_lines": last,
        }[e.control.data]
        await self.save_unsaved()
        await self._show_window(target)

    def _last_window_start(self) -> int:
        if not self.ordered:
            return 0
        return (len(self.ordered) - 1) // WINDOW_SIZE * WINDOW_SIZE

    async def _show_window(self, start: int) -> None:
        """
        A window can start anywhere, not only on a multiple of `WINDOW_SIZE`, so one
        opened on a found line keeps it at the top. Only a start past the end, left by
        deleting the last window's only line, falls back to the last whole window.
        """
        start = self._last_window_start() if start >= len(self.ordered) else max(0, start)
        moved = start != self.window_start
        self.window_start = start

        shown = self.ordered[start : start + WINDOW_SIZE]
        total = len(self.ordered)
        for pager in (self.pager, self.bottom_pager):
            pager.show(start, shown, total, self.timed)

        rows: list[ft.Control] = [self._row(line) for line in shown]
        if self.bottom_pager.visible:
            rows.append(self.bottom_pager)
        self.line_list.controls = rows

        self._refresh()
        if moved:
            await self._scroll_to_top()

    async def _scroll_to_top(self) -> None:
        """A new window should start at its first line, not where the last one was left."""
        try:
            await self.line_list.scroll_to(offset=0)
        except (RuntimeError, AssertionError):
            pass

    def _show_message(self, message: str) -> None:
        self.pager.visible = self.bottom_pager.visible = False
        self.line_list.controls = [ft.Text(message, size=12, color=self.colors.muted)]
        self._refresh()

    def _refresh(self) -> None:
        try:
            self.update()
        except (RuntimeError, AssertionError):
            pass

    def _row(self, line: TranscriptLine) -> ft.Row:
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
                    self.speakers,
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

    def _shown_control(self, prefix: str, line_id: str) -> ft.TextField | ft.Dropdown | None:
        """The field on screen for one part of a line, if its row is in the window."""
        data = f"{prefix}:{line_id}"
        for row in self.line_list.controls:
            for control in getattr(row, "controls", []):
                if isinstance(control, ft.TextField | ft.Dropdown) and control.data == data:
                    return control
        return None

    async def save_unsaved(self) -> None:
        """
        Saves any text typed into the window that its line does not hold yet. Called
        before the rows are replaced (paging, reloading after a delete, leaving edit
        mode), so an edit does not depend on the field's blur reaching us: the Flet
        client sends no blur for a focused field that is removed from the screen. A
        field the blur already saved matches its line by now, so nothing is saved twice.
        """
        saves = []
        for row in self.line_list.controls:
            for control in getattr(row, "controls", []):
                if not isinstance(control, ft.TextField) or not control.data:
                    continue
                line = self._line_for(control)
                typed = control.value or ""
                if line is not None and typed != line.text:
                    saves.append(self._start_save(line, "text", typed))
        if saves:
            await asyncio.gather(*saves)

    async def text_blurred(self, e) -> None:
        """
        A blur fires whether or not anything was typed, so unchanged text is ignored.
        See `_start_save` for when the line takes the new text, and how a failure is
        undone.
        """
        control = e.control
        line = self._line_for(control)
        if line is None:
            return

        typed = control.value or ""
        if typed == line.text:
            return

        await self._start_save(line, "text", typed)

    async def speaker_changed(self, e) -> None:
        control = e.control
        line = self._line_for(control)
        if line is None:
            return

        chosen = chosen_value(control)
        if not chosen or chosen == line.speaker_name:
            return

        if await self._start_save(line, "speaker_name", chosen) and chosen not in self.speakers:
            self.speakers.append(chosen)

    def _start_save(self, line: TranscriptLine, field: str, value: str) -> Awaitable[bool]:
        """
        Puts `value` on the line now and returns the save to await.

        The line takes the value before the save runs, not after. Paging away is what
        blurs a text field, so paging straight back can rebuild the row while the save is
        still running; built from the old text, that row would save the old text over the
        correction the next time it is blurred.

        That makes a failure harder to undo: by the time one save fails, a later edit of
        the same field may have been saved, or still be running. So nothing is put back
        until the field's last running save ends, and then the line and its row get the
        value the database is known to hold.
        """
        key = (field, str(line.id))
        saves = self._saves.get(key)
        if saves is None:
            saves = self._saves[key] = _Saves(confirmed=getattr(line, field))
        saves.pending += 1
        setattr(line, field, value)
        return self._finish_save(line, field, value, saves)

    async def _finish_save(
        self, line: TranscriptLine, field: str, value: str, saves: _Saves
    ) -> bool:
        saved = await self._save(line, **{field: value})
        saves.pending -= 1
        if saved:
            saves.confirmed = value
        if saves.pending == 0:
            self._saves.pop((field, str(line.id)), None)
            self._settle(line, field, saves.confirmed)
        return saved

    def _settle(self, line: TranscriptLine, field: str, confirmed: str | None) -> None:
        """
        Gives the line, and the row showing it, the value the database holds. The row is
        looked up again rather than taken from the event: by now the window may have
        moved and come back, so the control that started the save may not be on screen.
        A reload during the save may also have replaced the line object.
        """
        key = str(line.id)
        setattr(line, field, confirmed)
        current = self.lines.get(key)
        if current is not None and current is not line:
            setattr(current, field, confirmed)
        prefix = "text" if field == "text" else "speaker"
        control = self._shown_control(prefix, key)
        if control is not None and control.value != confirmed:
            control.value = confirmed
            self._repaint(control)

    async def _save(self, line: TranscriptLine, **changes) -> bool:
        """
        The failure names the line by its time: paging away is what starts a save, so by
        the time it fails the row may no longer be on screen.
        """
        try:
            await self.transcript_service.update_line(self.chronicle.id, line.id, **changes)
        except Exception as error:
            logger.exception("Could not save a transcript line")
            self.show_snackbar(
                t(
                    "transcript.line_save_failed",
                    time=format_timestamp(line.start_time),
                    error=error,
                )
            )
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

        # Before the delete, so text still unsaved in this very row is not saved to a
        # line that is gone.
        await self.save_unsaved()
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
