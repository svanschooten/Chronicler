"""
Editing a transcript one line at a time.

Whole-blob editing was the obvious alternative and is worse: parsing the text back into
lines would have to guess where speaker turns and timings belong, and a single
mis-parsed line would silently rewrite the ones around it. Editing one part of one line
at a time means an edit touches exactly the line it was typed into.

Edit mode reads like the transcript: each line is plain text in the reader's style, and
only the part that is clicked becomes a control. See docs/transcript-editing.md and
docs/superpowers/specs/2026-11-13-inline-transcript-editor-design.md.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import flet as ft

from chronicler.core.database_manager import NewerSchemaError
from chronicler.core.formatting import format_timestamp, looks_synthetic
from chronicler.core.models import Chronicle, TranscriptLine
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.desktop.dialogs import confirm
from chronicler.desktop.theme import ThemeColors
from chronicler.desktop.views.transcript.style import TRANSCRIPT_STYLE, TRANSCRIPT_TEXT_SIZE
from chronicler.desktop.widgets import MENU_HEIGHT
from chronicler.i18n import format_count, t

logger = logging.getLogger(__name__)

CONFIRMATION_EXCERPT = 60
WINDOW_SIZE = 100
SPEAKER_PICKER_WIDTH = 180
DELETE_BUTTON_SIZE = 20
OPEN_BAR_WIDTH = 2


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


TEXT = "text"
SPEAKER = "speaker"
# How long a speaker picker that lost focus stays on screen. A click on one of its menu
# options can blur the field before the pick arrives; closing at once would take the menu
# away with the pick still on its way.
PICKER_BLUR_GRACE = 0.3


@dataclass
class _Open:
    """The one part of one line that has its control on screen."""

    line_id: str
    part: str
    control: ft.TextField | ft.Dropdown


class LineRow(ft.Container):
    """
    One transcript line, shown the way the reading view shows it: `[time] Speaker: text`
    as one wrapping text in the reader's style. The speaker and the text are spans that
    open their own control when clicked; the timestamp is not clickable. See
    docs/transcript-editing.md.
    """

    def __init__(self, line: TranscriptLine, editor: "TranscriptEditor"):
        self.line_id = str(line.id)
        self.editor = editor
        self.hovered = False
        self.is_open = False
        # Kept in the layout and only faded in, so the text does not rewrap under the
        # mouse as the button appears.
        # Sized to one text line, so it does not make short rows taller than long ones.
        self.delete_button = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE,
            icon_size=15,
            width=DELETE_BUTTON_SIZE,
            height=DELETE_BUTTON_SIZE,
            padding=0,
            style=ft.ButtonStyle(padding=0),
            icon_color=editor.colors.muted,
            data=self.line_id,
            tooltip=t("transcript.delete_line"),
            on_click=editor.delete_clicked,
            opacity=0,
        )
        self.body: ft.Control = ft.Text()
        self.layout = ft.Row(
            vertical_alignment=ft.CrossAxisAlignment.START,
            spacing=4,
            controls=[self.body, self.delete_button],
        )
        super().__init__(
            key=self.line_id,
            content=self.layout,
            padding=ft.Padding(left=4, top=1, right=0, bottom=1),
            border_radius=4,
            on_hover=self.hover_changed,
        )
        self.show_line(line)

    def _timestamp_span(self, line: TranscriptLine) -> ft.TextSpan:
        return ft.TextSpan(
            f"[{format_timestamp(line.start_time)}] ",
            style=ft.TextStyle(color=self.editor.colors.muted, font_family="monospace"),
        )

    @staticmethod
    def _speaker_label(line: TranscriptLine) -> str:
        return f"{line.speaker_name or t('common.unknown')}: "

    def _text(self, spans: list[ft.TextSpan], expand: bool = True) -> ft.Text:
        return ft.Text(
            spans=spans,
            style=TRANSCRIPT_STYLE,
            color=self.editor.colors.text,
            expand=expand,
        )

    def show_line(self, line: TranscriptLine) -> None:
        """Plain text, with the speaker and the text each clickable."""
        if line.text:
            text_span = ft.TextSpan(line.text, data=self.line_id, on_click=self.editor.text_clicked)
        else:
            # An empty line still needs something to click.
            text_span = ft.TextSpan(
                t("transcript.empty_line"),
                data=self.line_id,
                style=ft.TextStyle(color=self.editor.colors.muted, italic=True),
                on_click=self.editor.text_clicked,
            )
        self.is_open = False
        self._set_body(
            self._text(
                [
                    self._timestamp_span(line),
                    ft.TextSpan(
                        self._speaker_label(line),
                        data=self.line_id,
                        on_click=self.editor.speaker_clicked,
                    ),
                    text_span,
                ]
            )
        )

    def show_text_field(self, line: TranscriptLine, field: ft.TextField) -> None:
        """The time and speaker stay as they were; only the text becomes a field."""
        self.is_open = True
        self._set_body(
            ft.Row(
                expand=True,
                spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    self._text(
                        [self._timestamp_span(line), ft.TextSpan(self._speaker_label(line))],
                        expand=False,
                    ),
                    field,
                ],
            )
        )

    def show_speaker_picker(self, line: TranscriptLine, picker: ft.Dropdown) -> None:
        """The time and text stay as they were; only the speaker becomes a picker."""
        self.is_open = True
        self._set_body(
            ft.Row(
                expand=True,
                spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    self._text([self._timestamp_span(line)], expand=False),
                    picker,
                    self._text([ft.TextSpan(f": {line.text}")]),
                ],
            )
        )

    def _set_body(self, body: ft.Control) -> None:
        self.body = body
        self.layout.controls[0] = body
        self._paint_hover()

    def hover_changed(self, e) -> None:
        self.hovered = e.data is True or e.data == "true"
        self._paint_hover()
        self.repaint()

    def _paint_hover(self) -> None:
        """
        The open row also gets an accent bar on its left: its field is borderless and in
        the reader's style, so without one nothing shows that it is being edited. The bar
        is always there, transparent when closed, so opening shifts no text.
        """
        lit = self.hovered or self.is_open
        self.bgcolor = self.editor.colors.hover if lit else None
        self.delete_button.opacity = 1 if lit else 0
        self.border = ft.Border(
            left=ft.BorderSide(
                OPEN_BAR_WIDTH,
                self.editor.colors.accent if self.is_open else ft.Colors.TRANSPARENT,
            )
        )

    def repaint(self) -> None:
        try:
            self.update()
        except (RuntimeError, AssertionError):
            pass


class TranscriptEditor(ft.Column):
    """
    Edit mode: the transcript as it reads, a window of rows at a time, with one part of
    one line open for editing at most. See docs/transcript-editing.md.
    """

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
        self.rows: dict[str, LineRow] = {}
        self.open: _Open | None = None
        # Keyed by (field, line id). See `_start_save`.
        self._saves: dict[tuple[str, str], _Saves] = {}
        self.ordered: list[TranscriptLine] = []
        self.speakers: list[str] = []
        self.window_start = 0
        # False when the timings are line indices, which say nothing as a time span.
        self.timed = False
        self._keys_page: ft.Page | None = None
        self._previous_key_handler: Any = None

        self.line_list = ft.ListView(spacing=0, expand=True)
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
        can only scroll to a row the client has already built, so the top is the one
        place it is sure to be seen.
        """
        self._listen_for_keys()
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

    async def finish_editing(self) -> None:
        """Before the editor leaves the screen: save what is open and stop handling keys."""
        await self.save_unsaved()
        self._stop_listening_for_keys()

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

        # Whatever was open belonged to rows that are about to go.
        self.open = None
        self.rows = {str(line.id): LineRow(line, self) for line in shown}
        rows: list[ft.Control] = list(self.rows.values())
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
        self.open = None
        self.rows = {}
        self.line_list.controls = [ft.Text(message, size=12, color=self.colors.muted)]
        self._refresh()

    def _refresh(self) -> None:
        try:
            self.update()
        except (RuntimeError, AssertionError):
            pass

    # Opening and closing a part of a line

    async def text_clicked(self, e) -> None:
        await self._open_part(str(e.control.data), TEXT)

    async def speaker_clicked(self, e) -> None:
        await self._open_part(str(e.control.data), SPEAKER)

    async def _open_part(self, line_id: str, part: str) -> None:
        """
        Closes whatever is open, saving a text field, then swaps this part for its
        control and focuses it. `focus()` rather than `autofocus`: Flet honours
        `autofocus` only for the first such control added to the page.
        """
        opened = self.open
        if opened is not None and opened.line_id == line_id and opened.part == part:
            return
        # The save of what was open runs while the new part opens, not before it.
        pending = self._close(save=True)

        line = self.lines.get(line_id)
        row = self.rows.get(line_id)
        if line is None or row is None:
            if pending is not None:
                await pending
            return

        control: ft.TextField | ft.Dropdown
        if part == TEXT:
            control = self._text_field(line)
            row.show_text_field(line, control)
        else:
            control = self._speaker_picker(line)
            row.show_speaker_picker(line, control)
        self.open = _Open(line_id, part, control)
        row.repaint()
        try:
            await control.focus()
        except (RuntimeError, AssertionError):
            pass
        if pending is not None:
            await pending

    def _text_field(self, line: TranscriptLine) -> ft.TextField:
        """Borderless and in the reader's style, so opening it moves no words around."""
        return ft.TextField(
            data=str(line.id),
            value=line.text,
            expand=True,
            multiline=True,
            min_lines=1,
            shift_enter=True,
            border=ft.InputBorder.NONE,
            dense=True,
            content_padding=0,
            text_style=TRANSCRIPT_STYLE,
            color=self.colors.text,
            autofocus=True,
            on_submit=self.text_submitted,
            on_blur=self.text_blurred,
        )

    def _speaker_picker(self, line: TranscriptLine) -> ft.Dropdown:
        """
        Opens empty, so typing filters at once, with the line's speaker as the hint so it
        never looks deleted. Its options are built now, for this picker only.
        """
        return ft.Dropdown(
            data=str(line.id),
            value=None,
            hint_text=line.speaker_name or t("common.unknown"),
            hint_style=ft.TextStyle(color=self.colors.muted),
            options=[ft.DropdownOption(key=name, text=name) for name in self.speakers],
            editable=True,
            enable_filter=True,
            menu_height=MENU_HEIGHT,
            width=SPEAKER_PICKER_WIDTH,
            dense=True,
            border=ft.InputBorder.UNDERLINE,
            content_padding=ft.Padding(left=0, top=2, right=0, bottom=2),
            text_size=TRANSCRIPT_TEXT_SIZE,
            on_select=self.speaker_picked,
            on_blur=self.speaker_blurred,
        )

    def _is_open(self, control: ft.Control) -> bool:
        """A late event from a control already closed must not act on the line again."""
        return self.open is not None and self.open.control is control

    async def close_open(self, save: bool = True) -> None:
        """Puts the open part back as text and waits for its save, if it started one."""
        pending = self._close(save)
        if pending is not None:
            await pending

    def _close(self, save: bool) -> Awaitable[bool] | None:
        """
        Puts the open part back as text and returns the save to await, if `save` is set
        and a text field holds a change.

        The control's value is read here, on the server side, and the save is started
        explicitly: the control is being removed, and the Flet client sends no blur for a
        focused field it takes off the screen. `open` is cleared first, so the blur that
        may still arrive for it finds it closed and does nothing. A speaker picker never
        saves on close: only a pick does.
        """
        opened = self.open
        if opened is None:
            return None
        self.open = None

        line = self.lines.get(opened.line_id)
        row = self.rows.get(opened.line_id)
        pending: Awaitable[bool] | None = None
        if save and line is not None and opened.part == TEXT:
            typed = opened.control.value or ""
            if typed != line.text:
                pending = self._start_save(line, "text", typed)
        if row is not None and line is not None:
            row.show_line(line)
            row.repaint()
        return pending

    async def save_unsaved(self) -> None:
        """
        Saves and closes the open part before the rows are replaced (paging, reloading
        after a delete, leaving edit mode). Only one part can be open, so that is all
        there is to save.
        """
        await self.close_open(save=True)

    async def text_submitted(self, e) -> None:
        """Enter saves and closes; Shift+Enter is a newline (`shift_enter`)."""
        if self._is_open(e.control):
            await self.close_open(save=True)

    async def text_blurred(self, e) -> None:
        """
        A blur fires whether or not anything was typed; `close_open` ignores unchanged
        text. See `_start_save` for when the line takes the new text, and how a failure
        is undone.
        """
        if self._is_open(e.control):
            await self.close_open(save=True)

    async def speaker_picked(self, e) -> None:
        """
        Only a pick saves a speaker. A name typed and left without picking is not saved:
        a half-typed filter must never become a speaker.
        """
        control = e.control
        line = self.lines.get(str(control.data))
        if line is None or not self._is_open(control):
            return
        chosen = (control.value or "").strip()
        await self.close_open(save=False)
        if not chosen or chosen == line.speaker_name:
            return

        saved = await self._start_save(line, "speaker_name", chosen)
        if saved:
            self._learn_speaker(line.speaker_name or chosen)

    async def speaker_blurred(self, e) -> None:
        """
        Leaving the picker with something typed closes it without saving, after
        `PICKER_BLUR_GRACE`: a click on one of its options blurs the field before the
        pick arrives, and closing at once would take the menu away under the click.

        Leaving it with nothing typed keeps it open. A click on the picker's own arrow
        blurs the field while it opens the menu (found in PR #92), and closing then would
        make the arrow useless. An empty picker only shows the current name as its hint,
        so it cannot look like a change; it closes on the next click on a line, Esc, a
        pick, paging or finishing.
        """
        control = e.control
        if not self._is_open(control):
            return
        await asyncio.sleep(PICKER_BLUR_GRACE)
        if self._is_open(control) and (control.text or "").strip():
            await self.close_open(save=False)

    def _learn_speaker(self, name: str) -> None:
        """A name saved here is offered by the next picker without reloading."""
        if name and name not in self.speakers:
            self.speakers.append(name)
            self.speakers.sort(key=str.casefold)

    # Keys

    def _listen_for_keys(self) -> None:
        """
        Esc goes through the page's key handler, installed only while editing and handing
        on to whatever handler was there before.
        """
        try:
            page = self.page
        except (RuntimeError, AssertionError):
            return
        if page is None or self._keys_page is page:
            return
        self._keys_page = page
        self._previous_key_handler = page.on_keyboard_event
        page.on_keyboard_event = self.key_pressed

    def _stop_listening_for_keys(self) -> None:
        page = self._keys_page
        if page is None:
            return
        if page.on_keyboard_event == self.key_pressed:
            page.on_keyboard_event = self._previous_key_handler
        self._keys_page = None
        self._previous_key_handler = None

    async def key_pressed(self, e) -> None:
        if e.key == "Escape" and self.open is not None:
            await self.close_open(save=False)
            return
        previous = self._previous_key_handler
        if previous is not None:
            result = previous(e)
            if asyncio.iscoroutine(result):
                await result

    # Saving

    def _start_save(self, line: TranscriptLine, field: str, value: str) -> Awaitable[bool]:
        """
        Puts `value` on the line now and returns the save to await.

        The line takes the value before the save runs, not after. Closing a field shows
        the line's text at once, and paging can rebuild the row while the save is still
        running; built from the old text, either would show the edit as lost.

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
        stored = await self._save(line, **{field: value})
        saves.pending -= 1
        if stored is not None:
            saves.confirmed = stored
        if saves.pending == 0:
            self._saves.pop((field, str(line.id)), None)
            self._settle(line, field, saves.confirmed)
        return stored is not None

    def _settle(self, line: TranscriptLine, field: str, confirmed: str | None) -> None:
        """
        Gives the line, and the row showing it, the value the database holds. The row is
        looked up again rather than taken from the event: by now the window may have
        moved and come back. A reload during the save may also have replaced the line
        object. If that part is open again, its control is corrected instead.
        """
        key = str(line.id)
        setattr(line, field, confirmed)
        current = self.lines.get(key)
        if current is not None and current is not line:
            setattr(current, field, confirmed)
        shown = current or line

        row = self.rows.get(key)
        if row is None:
            return
        opened = self.open
        if opened is not None and opened.line_id == key:
            if field == "text" and opened.part == TEXT and opened.control.value != confirmed:
                opened.control.value = confirmed
                self._repaint(opened.control)
            return
        row.show_line(shown)
        row.repaint()

    async def _save(self, line: TranscriptLine, **changes) -> str | None:
        """
        Returns the value the database now holds, or None when the save failed. For a
        speaker that is the chronicle's spelling, which may differ in case from what was
        picked (ticket 083).

        The failure names the line by its time: closing the field is what starts a save,
        so by the time it fails the row may no longer be on screen.
        """
        field, value = next(iter(changes.items()))
        try:
            saved = await self.transcript_service.update_line(self.chronicle.id, line.id, **changes)
        except Exception as error:
            logger.exception("Could not save a transcript line")
            self.show_snackbar(
                t(
                    "transcript.line_save_failed",
                    time=format_timestamp(line.start_time),
                    error=error,
                )
            )
            return None
        stored = getattr(saved, field, None)
        return stored if isinstance(stored, str) and stored else value

    async def delete_clicked(self, e) -> None:
        line = self.lines.get(str(e.control.data))
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
