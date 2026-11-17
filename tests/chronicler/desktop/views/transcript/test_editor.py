"""Tests for the per-line transcript editor."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import flet as ft
import pytest

from chronicler.core.models import Chronicle, TranscriptLine
from chronicler.desktop.theme import theme_colors
from chronicler.desktop.views.transcript.editor import (
    WINDOW_SIZE,
    LinePager,
    LineRow,
    TranscriptEditor,
)
from chronicler.desktop.views.transcript.style import TRANSCRIPT_STYLE
from chronicler.i18n import set_locale, t
from tests.chronicler.desktop.controls import find_controls


def _line(text="Some words", speaker="Nyx", start=0.0):
    return TranscriptLine(speaker_name=speaker, text=text, start_time=start, end_time=start + 1)


@pytest.fixture
def make_editor():
    def _make(lines=None, speakers=None):
        transcript_service = AsyncMock()
        transcript_service.get_transcript.return_value = lines if lines is not None else [_line()]
        transcript_service.speaker_suggestions.return_value = speakers or ["Nyx", "Vale"]
        editor = TranscriptEditor(
            Chronicle(title="Session One"),
            transcript_service,
            theme_colors(True),
            MagicMock(),
            AsyncMock(),
        )
        editor.line_list.update = MagicMock()
        return editor, transcript_service

    return _make


def _row(editor, index=0) -> LineRow:
    return editor.line_list.controls[index]


def _spans(row: LineRow) -> list[ft.TextSpan]:
    """The time, speaker and text spans of a row showing its line as text."""
    assert isinstance(row.body, ft.Text), "the row has a part open"
    return row.body.spans or []


def _shown_text(row: LineRow) -> str:
    return _spans(row)[2].text or ""


def _shown_speaker(row: LineRow) -> str:
    return _spans(row)[1].text or ""


async def _open_text(editor, index=0) -> ft.TextField:
    """Clicks a row's text, as the client does, and returns the field it opened."""
    await editor.text_clicked(MagicMock(control=_spans(_row(editor, index))[2]))
    assert isinstance(editor.open.control, ft.TextField)
    return editor.open.control


async def _open_speaker(editor, index=0) -> ft.Dropdown:
    await editor.speaker_clicked(MagicMock(control=_spans(_row(editor, index))[1]))
    assert isinstance(editor.open.control, ft.Dropdown)
    return editor.open.control


async def _edit_text(editor, value, index=0) -> ft.TextField:
    """Opens a row's text, types `value` and leaves the field, which saves it."""
    field = await _open_text(editor, index)
    field.value = value
    await editor.text_blurred(MagicMock(control=field))
    return field


async def _pick(editor, name, index=0) -> ft.Dropdown:
    picker = await _open_speaker(editor, index)
    picker.value = name
    await editor.speaker_picked(MagicMock(control=picker))
    return picker


class TestLoading:
    @pytest.mark.asyncio
    async def test_one_row_per_line(self, make_editor):
        editor, _ = make_editor([_line("First"), _line("Second", start=1.0)])

        await editor.load()

        assert len(editor.line_list.controls) == 2

    @pytest.mark.asyncio
    async def test_each_row_reads_like_the_reader(self, make_editor):
        """`Speaker: text`, as one wrapping text in the reader's style."""
        editor, _ = make_editor([_line("Hello there", speaker="Vale", start=3725.0)])

        await editor.load()

        row = _row(editor)
        assert [span.text for span in _spans(row)] == ["[01:02:05] ", "Vale: ", "Hello there"]
        assert row.body.style == TRANSCRIPT_STYLE

    @pytest.mark.asyncio
    async def test_rows_hold_no_form_controls_until_clicked(self, make_editor):
        """Ticket 056's cost: every row used to carry a dropdown of every speaker."""
        editor, _ = make_editor(_long(WINDOW_SIZE), speakers=[f"Name {i}" for i in range(40)])

        await editor.load()

        assert find_controls(editor.line_list, lambda c: isinstance(c, ft.Dropdown)) == []
        assert find_controls(editor.line_list, lambda c: isinstance(c, ft.TextField)) == []

    @pytest.mark.asyncio
    async def test_the_speaker_and_the_text_can_be_clicked_but_not_the_time(self, make_editor):
        editor, _ = make_editor()

        await editor.load()

        time, speaker, text = _spans(_row(editor))
        assert time.on_click is None
        assert speaker.on_click is not None
        assert text.on_click is not None

    @pytest.mark.asyncio
    async def test_a_line_without_a_speaker_says_unknown(self, make_editor):
        editor, _ = make_editor([_line(speaker=None)])

        await editor.load()

        assert _shown_speaker(_row(editor)) == f"{t('common.unknown')}: "

    @pytest.mark.asyncio
    async def test_an_empty_line_still_has_something_to_click(self, make_editor):
        editor, _ = make_editor([_line("")])

        await editor.load()

        text = _spans(_row(editor))[2]
        assert text.text == t("transcript.empty_line")
        assert text.on_click is not None

    @pytest.mark.asyncio
    async def test_an_empty_transcript_says_so(self, make_editor):
        editor, _ = make_editor([])

        await editor.load()

        assert len(editor.line_list.controls) == 1
        assert isinstance(editor.line_list.controls[0], ft.Text)

    @pytest.mark.asyncio
    async def test_a_failing_load_degrades_rather_than_raising(self, make_editor):
        editor, service = make_editor()
        service.get_transcript.side_effect = RuntimeError("no such table")

        await editor.load()

        assert isinstance(editor.line_list.controls[0], ft.Text)

    @pytest.mark.asyncio
    async def test_rows_are_scrollable_so_a_long_transcript_stays_usable(self, make_editor):
        editor, _ = make_editor([_line(f"Line {i}", start=float(i)) for i in range(50)])

        await editor.load()

        assert isinstance(editor.line_list, ft.ListView)
        assert len(editor.line_list.controls) == 50

    @pytest.mark.asyncio
    async def test_each_row_is_keyed_by_its_line_so_it_can_be_scrolled_to(self, make_editor):
        line = _line()
        editor, _ = make_editor([line])

        await editor.load()

        assert _row(editor).key == str(line.id)


class TestHover:
    @pytest.mark.asyncio
    async def test_the_row_under_the_mouse_is_tinted_and_shows_delete(self, make_editor):
        editor, _ = make_editor()
        await editor.load()
        row = _row(editor)

        row.hover_changed(MagicMock(data=True))

        assert row.bgcolor == editor.colors.hover
        assert row.delete_button.opacity == 1

    @pytest.mark.asyncio
    async def test_leaving_the_row_takes_the_tint_and_delete_away(self, make_editor):
        editor, _ = make_editor()
        await editor.load()
        row = _row(editor)
        row.hover_changed(MagicMock(data=True))

        row.hover_changed(MagicMock(data=False))

        assert row.bgcolor is None
        assert row.delete_button.opacity == 0

    @pytest.mark.asyncio
    async def test_a_row_being_edited_stays_tinted(self, make_editor):
        editor, _ = make_editor()
        await editor.load()

        await _open_text(editor)

        assert _row(editor).bgcolor == editor.colors.hover
        assert _row(editor).delete_button.opacity == 1


def _long(count):
    return [_line(f"Line {i}", start=float(i)) for i in range(count)]


def _rows(editor) -> list:
    """The line rows, without the pager that ends a window of a long transcript."""
    return [c for c in editor.line_list.controls if not isinstance(c, LinePager)]


def _texts(editor) -> list[str]:
    return [_shown_text(row) for row in _rows(editor)]


async def _press(editor, button):
    await editor.pager_clicked(MagicMock(control=button))


class TestWindow:
    @pytest.mark.asyncio
    async def test_a_short_transcript_shows_every_line_and_no_pager(self, make_editor):
        editor, _ = make_editor(_long(WINDOW_SIZE))

        await editor.load()

        assert len(editor.line_list.controls) == WINDOW_SIZE
        assert editor.pager.visible is False

    @pytest.mark.asyncio
    async def test_a_long_transcript_builds_only_the_first_window(self, make_editor):
        editor, _ = make_editor(_long(1686))

        await editor.load()

        assert len(_rows(editor)) == WINDOW_SIZE
        assert _texts(editor)[0] == "Line 0"
        assert editor.pager.visible is True
        assert "1-100" in editor.pager.label.value
        assert "1,686" in editor.pager.label.value

    @pytest.mark.asyncio
    async def test_the_line_count_is_written_the_local_way(self, make_editor):
        editor, _ = make_editor(_long(1686))
        set_locale("de")
        try:
            await editor.load()
        finally:
            set_locale("en")

        assert "1.686" in editor.pager.label.value

    @pytest.mark.asyncio
    async def test_next_and_previous_move_one_window(self, make_editor):
        editor, _ = make_editor(_long(250))
        await editor.load()

        await _press(editor, editor.pager.next_button)
        assert _texts(editor)[0] == f"Line {WINDOW_SIZE}"

        await _press(editor, editor.pager.previous_button)
        assert _texts(editor)[0] == "Line 0"

    @pytest.mark.asyncio
    async def test_last_shows_the_remainder_and_first_goes_back(self, make_editor):
        editor, _ = make_editor(_long(250))
        await editor.load()

        await _press(editor, editor.pager.last_button)
        assert _texts(editor) == [f"Line {i}" for i in range(200, 250)]
        assert "201-250" in editor.pager.label.value

        await _press(editor, editor.pager.first_button)
        assert _texts(editor)[0] == "Line 0"

    @pytest.mark.asyncio
    async def test_the_label_gives_the_window_time_span(self, make_editor):
        """The reader shows times, so a time is how a passage found there is known."""
        lines = [
            TranscriptLine(
                speaker_name="Nyx",
                text=f"Line {i}",
                start_time=i * 2.5,
                end_time=i * 2.5 + 2.0,
                synthetic_timing=False,
            )
            for i in range(250)
        ]
        editor, _ = make_editor(lines)
        await editor.load()

        await _press(editor, editor.pager.next_button)

        assert "00:04:10-00:08:19" in editor.pager.label.value
        assert "101-200" in editor.pager.label.value

    @pytest.mark.asyncio
    async def test_line_indices_are_not_shown_as_a_time_span(self, make_editor):
        lines = [
            TranscriptLine(
                speaker_name="Nyx",
                text=f"Line {i}",
                start_time=float(i),
                end_time=float(i + 1),
                synthetic_timing=True,
            )
            for i in range(250)
        ]
        editor, _ = make_editor(lines)

        await editor.load()

        assert ":" not in editor.pager.label.value

    @pytest.mark.asyncio
    async def test_a_long_transcript_ends_each_window_with_a_pager(self, make_editor):
        """Reaching the end of a window should not mean scrolling back up to move on."""
        editor, _ = make_editor(_long(250))

        await editor.load()

        assert editor.line_list.controls[-1] is editor.bottom_pager
        assert editor.bottom_pager.visible is True
        assert editor.bottom_pager.label.value == editor.pager.label.value

    @pytest.mark.asyncio
    async def test_a_short_transcript_has_no_pager_at_the_end(self, make_editor):
        editor, _ = make_editor(_long(WINDOW_SIZE))

        await editor.load()

        assert editor.bottom_pager not in editor.line_list.controls

    @pytest.mark.asyncio
    async def test_the_pager_at_the_end_moves_the_window_too(self, make_editor):
        editor, _ = make_editor(_long(250))
        await editor.load()
        editor.line_list.scroll_to = AsyncMock()

        await _press(editor, editor.bottom_pager.next_button)

        assert _texts(editor)[0] == f"Line {WINDOW_SIZE}"
        assert editor.bottom_pager.label.value == editor.pager.label.value
        editor.line_list.scroll_to.assert_awaited_once_with(offset=0)

    @pytest.mark.asyncio
    async def test_both_pagers_disable_the_same_buttons(self, make_editor):
        editor, _ = make_editor(_long(250))
        await editor.load()

        await _press(editor, editor.bottom_pager.last_button)

        for pager in (editor.pager, editor.bottom_pager):
            assert pager.next_button.disabled and pager.last_button.disabled
            assert not pager.previous_button.disabled

    @pytest.mark.asyncio
    async def test_buttons_that_lead_nowhere_are_disabled(self, make_editor):
        editor, _ = make_editor(_long(250))
        await editor.load()

        assert editor.pager.first_button.disabled and editor.pager.previous_button.disabled
        assert not editor.pager.next_button.disabled

        await _press(editor, editor.pager.last_button)

        assert editor.pager.next_button.disabled and editor.pager.last_button.disabled
        assert not editor.pager.previous_button.disabled

    @pytest.mark.asyncio
    async def test_a_line_on_a_later_window_still_saves(self, make_editor):
        editor, service = make_editor(_long(250))
        await editor.load()
        await _press(editor, editor.pager.next_button)

        await _edit_text(editor, "Corrected")

        assert service.update_line.await_args.kwargs["text"] == "Corrected"

    @pytest.mark.asyncio
    async def test_deleting_keeps_the_window_that_was_showing(self, make_editor, attach_page):
        lines = _long(250)
        editor, service = make_editor(lines)
        attach_page(TranscriptEditor)
        await editor.load()
        await _press(editor, editor.pager.next_button)
        button = _row(editor).delete_button
        service.get_transcript.return_value = lines[:100] + lines[101:]

        with patch(
            "chronicler.desktop.views.transcript.editor.confirm",
            new=AsyncMock(return_value=True),
        ):
            await editor.delete_clicked(MagicMock(control=button))

        assert _texts(editor)[0] == "Line 101"

    @pytest.mark.asyncio
    async def test_a_window_past_the_end_falls_back_to_the_last(self, make_editor):
        """Deleting the only line on the last window must not leave an empty page."""
        lines = _long(101)
        editor, service = make_editor(lines)
        await editor.load()
        await _press(editor, editor.pager.last_button)
        service.get_transcript.return_value = lines[:100]

        await editor.load()

        assert _texts(editor)[0] == "Line 0"
        assert editor.pager.visible is False

    @pytest.mark.asyncio
    async def test_moving_to_another_window_scrolls_to_its_top(self, make_editor):
        editor, _ = make_editor(_long(250))
        await editor.load()
        editor.line_list.scroll_to = AsyncMock()

        await _press(editor, editor.pager.next_button)

        editor.line_list.scroll_to.assert_awaited_once_with(offset=0)

    @pytest.mark.asyncio
    async def test_reloading_the_same_window_keeps_the_scroll_position(self, make_editor):
        """A delete reloads the window; jumping to its top would lose your place."""
        editor, _ = make_editor(_long(250))
        await editor.load()
        await _press(editor, editor.pager.next_button)
        editor.line_list.scroll_to = AsyncMock()

        await editor.load()

        editor.line_list.scroll_to.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_line_to_show_opens_a_window_starting_at_it(self, make_editor):
        """A ListView cannot scroll to a row, so the found line goes at the top."""
        lines = _long(1686)
        editor, _ = make_editor(lines)

        await editor.load(show_line=lines[1234].id)

        assert _texts(editor)[0] == "Line 1234"
        assert "1,235-1,334" in editor.pager.label.value

    @pytest.mark.asyncio
    async def test_a_line_near_the_end_still_starts_the_window(self, make_editor):
        lines = _long(1686)
        editor, _ = make_editor(lines)

        await editor.load(show_line=lines[1680].id)

        assert _texts(editor) == [f"Line {i}" for i in range(1680, 1686)]
        assert editor.pager.next_button.disabled

    @pytest.mark.asyncio
    async def test_paging_from_a_found_line_moves_a_whole_window(self, make_editor):
        lines = _long(1686)
        editor, _ = make_editor(lines)
        await editor.load(show_line=lines[1234].id)

        await _press(editor, editor.pager.previous_button)
        assert _texts(editor)[0] == "Line 1134"

        await _press(editor, editor.pager.last_button)
        assert _texts(editor)[0] == "Line 1600"

    @pytest.mark.asyncio
    async def test_a_line_to_show_that_is_gone_keeps_the_window(self, make_editor):
        """The match may have been deleted or cleaned away since the find ran."""
        editor, _ = make_editor(_long(250))
        await editor.load()
        await _press(editor, editor.pager.next_button)

        await editor.load(show_line=_line().id)

        assert _texts(editor)[0] == f"Line {WINDOW_SIZE}"

    @pytest.mark.asyncio
    async def test_editing_again_reopens_the_window_left_last_time(self, make_editor):
        """
        The view keeps one editor, and leaving edit mode to read a passage and coming
        back should not mean paging all the way there again.
        """
        editor, _ = make_editor(_long(250))
        await editor.load()
        await _press(editor, editor.pager.next_button)

        await editor.load()

        assert _texts(editor)[0] == f"Line {WINDOW_SIZE}"


class TestOpeningAPart:
    @pytest.mark.asyncio
    async def test_clicking_the_text_opens_a_field_holding_it(self, make_editor):
        editor, _ = make_editor([_line("Hello there", speaker="Vale")])
        await editor.load()

        field = await _open_text(editor)

        assert field.value == "Hello there"
        assert field.multiline is True
        assert field.shift_enter is True
        assert field.text_style == TRANSCRIPT_STYLE

    @pytest.mark.asyncio
    async def test_the_field_replaces_only_the_text(self, make_editor):
        """The time and speaker stay as they read, so nothing jumps."""
        editor, _ = make_editor([_line("Hello there", speaker="Vale", start=5.0)])
        await editor.load()

        await _open_text(editor)

        prefix = find_controls(_row(editor), lambda c: isinstance(c, ft.Text))[0]
        assert [span.text for span in prefix.spans] == ["[00:00:05] ", "Vale: "]

    @pytest.mark.asyncio
    async def test_the_opened_field_is_focused(self, make_editor):
        editor, _ = make_editor()
        await editor.load()

        with patch.object(ft.TextField, "focus", new=AsyncMock()) as focus:
            await _open_text(editor)

        focus.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_opening_another_part_closes_the_first(self, make_editor):
        editor, _ = make_editor([_line("First"), _line("Second", start=1.0)])
        await editor.load()
        await _open_text(editor, 0)

        await _open_text(editor, 1)

        assert _shown_text(_row(editor, 0)) == "First"
        assert editor.open.line_id == _row(editor, 1).line_id

    @pytest.mark.asyncio
    async def test_clicking_the_open_part_again_keeps_it_open(self, make_editor):
        editor, _ = make_editor()
        await editor.load()
        field = await _open_text(editor)
        field.value = "Half typed"

        await editor.text_clicked(MagicMock(control=MagicMock(data=_row(editor).line_id)))

        assert editor.open.control is field
        assert field.value == "Half typed"


class TestEditingText:
    @pytest.mark.asyncio
    async def test_a_changed_line_is_saved_on_blur(self, make_editor):
        editor, service = make_editor([_line("原文")])
        await editor.load()

        await _edit_text(editor, "Corrected")

        service.update_line.assert_awaited_once()
        assert service.update_line.await_args.kwargs["text"] == "Corrected"

    @pytest.mark.asyncio
    async def test_closing_shows_the_new_text(self, make_editor):
        editor, _ = make_editor([_line("Old")])
        await editor.load()

        await _edit_text(editor, "New")

        assert editor.open is None
        assert _shown_text(_row(editor)) == "New"

    @pytest.mark.asyncio
    async def test_enter_saves_and_closes(self, make_editor):
        editor, service = make_editor([_line("Old")])
        await editor.load()
        field = await _open_text(editor)
        field.value = "New"

        await editor.text_submitted(MagicMock(control=field))

        assert service.update_line.await_args.kwargs["text"] == "New"
        assert editor.open is None

    @pytest.mark.asyncio
    async def test_escape_discards_the_edit(self, make_editor):
        editor, service = make_editor([_line("Old")])
        await editor.load()
        field = await _open_text(editor)
        field.value = "Never mind"

        await editor.key_pressed(MagicMock(key="Escape"))

        service.update_line.assert_not_awaited()
        assert _shown_text(_row(editor)) == "Old"

    @pytest.mark.asyncio
    async def test_a_blur_after_escape_saves_nothing(self, make_editor):
        """Removing the field can still deliver its blur; the edit was discarded."""
        editor, service = make_editor([_line("Old")])
        await editor.load()
        field = await _open_text(editor)
        field.value = "Never mind"
        await editor.key_pressed(MagicMock(key="Escape"))

        await editor.text_blurred(MagicMock(control=field))

        service.update_line.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_opening_another_part_saves_the_open_text(self, make_editor):
        """The field is removed, and a removed field sends no blur."""
        editor, service = make_editor([_line("First"), _line("Second", start=1.0)])
        await editor.load()
        field = await _open_text(editor, 0)
        field.value = "First, corrected"

        await _open_speaker(editor, 1)

        service.update_line.assert_awaited_once()
        assert service.update_line.await_args.kwargs["text"] == "First, corrected"

    @pytest.mark.asyncio
    async def test_a_late_blur_from_a_closed_field_saves_nothing_twice(self, make_editor):
        editor, service = make_editor([_line("First"), _line("Second", start=1.0)])
        await editor.load()
        field = await _open_text(editor, 0)
        field.value = "First, corrected"
        await _open_text(editor, 1)

        await editor.text_blurred(MagicMock(control=field))

        service.update_line.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_an_unchanged_line_saves_nothing(self, make_editor):
        """Blur fires on every focus change, edited or not - same rule as Settings."""
        editor, service = make_editor([_line("Untouched")])
        await editor.load()

        await _edit_text(editor, "Untouched")

        service.update_line.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_second_edit_compares_against_the_first(self, make_editor):
        editor, service = make_editor([_line("One")])
        await editor.load()

        await _edit_text(editor, "Two")
        await _edit_text(editor, "Two")

        assert service.update_line.await_count == 1

    @pytest.mark.asyncio
    async def test_a_failed_save_is_reported_and_the_line_reverts(self, make_editor):
        editor, service = make_editor([_line("Original")])
        service.update_line.side_effect = RuntimeError("database is locked")
        await editor.load()

        await _edit_text(editor, "Attempted")

        editor.show_snackbar.assert_called_once()
        assert "database is locked" in editor.show_snackbar.call_args[0][0]
        assert _shown_text(_row(editor)) == "Original"
        assert editor.ordered[0].text == "Original"

    @pytest.mark.asyncio
    async def test_a_failed_save_says_which_line_it_was(self, make_editor):
        """The field is closed by the time the save fails."""
        editor, service = make_editor([_line("Original", start=3725.0)])
        service.update_line.side_effect = RuntimeError("database is locked")
        await editor.load()

        await _edit_text(editor, "Attempted")

        assert "01:02:05" in editor.show_snackbar.call_args[0][0]

    @pytest.mark.asyncio
    async def test_the_line_shows_the_new_text_while_it_saves(self, make_editor):
        editor, service = make_editor([_line("Old")])
        await editor.load()
        release = asyncio.Event()

        async def slow_save(*args, **kwargs):
            await release.wait()

        service.update_line.side_effect = slow_save

        saving = asyncio.create_task(_edit_text(editor, "New"))
        await asyncio.sleep(0)
        shown = _shown_text(_row(editor))
        release.set()
        await saving

        assert shown == "New"

    @pytest.mark.asyncio
    async def test_paging_back_during_a_save_shows_the_new_text(self, make_editor):
        editor, service = make_editor(_long(WINDOW_SIZE + 1))
        await editor.load()
        release = asyncio.Event()

        async def slow_save(*args, **kwargs):
            await release.wait()

        service.update_line.side_effect = slow_save

        saving = asyncio.create_task(_edit_text(editor, "Corrected"))
        await asyncio.sleep(0)
        await _press(editor, editor.pager.next_button)
        await _press(editor, editor.pager.previous_button)
        release.set()
        await saving

        assert _shown_text(_row(editor)) == "Corrected"
        assert service.update_line.await_count == 1

    @pytest.mark.asyncio
    async def test_a_save_failing_after_paging_back_repaints_the_rebuilt_row(self, make_editor):
        """The row that started the save is gone; the one on screen must not look saved."""
        editor, service = make_editor(_long(WINDOW_SIZE + 1))
        await editor.load()
        release = asyncio.Event()

        async def failing_save(*args, **kwargs):
            await release.wait()
            raise RuntimeError("database is locked")

        service.update_line.side_effect = failing_save

        saving = asyncio.create_task(_edit_text(editor, "Attempted"))
        await asyncio.sleep(0)
        await _press(editor, editor.pager.next_button)
        await _press(editor, editor.pager.previous_button)
        release.set()
        await saving

        assert _shown_text(_row(editor)) == "Line 0"
        assert editor.ordered[0].text == "Line 0"

    @pytest.mark.asyncio
    async def test_a_failure_corrects_the_field_if_the_line_is_open_again(self, make_editor):
        editor, service = make_editor([_line("Original")])
        await editor.load()
        release = asyncio.Event()

        async def failing_save(*args, **kwargs):
            await release.wait()
            raise RuntimeError("database is locked")

        service.update_line.side_effect = failing_save
        saving = asyncio.create_task(_edit_text(editor, "Attempted"))
        await asyncio.sleep(0)
        reopened = await _open_text(editor)
        release.set()
        await saving

        assert reopened.value == "Original"

    @pytest.mark.asyncio
    async def test_a_failure_after_a_later_edit_saved_keeps_the_later_edit(self, make_editor):
        """
        The first save fails after a second edit of the same line has saved. Putting back
        the text from before the first would show the line as unedited while the
        database holds the second edit.
        """
        editor, service = make_editor([_line("Original")])
        await editor.load()
        release_first = asyncio.Event()

        async def save(chronicle_id, line_id, **changes):
            if changes["text"] == "First":
                await release_first.wait()
                raise RuntimeError("database is locked")

        service.update_line.side_effect = save
        first = asyncio.create_task(_edit_text(editor, "First"))
        await asyncio.sleep(0)
        await _edit_text(editor, "Second")
        release_first.set()
        await first

        assert _shown_text(_row(editor)) == "Second"
        assert editor.ordered[0].text == "Second"

    @pytest.mark.asyncio
    async def test_a_later_failure_puts_back_the_last_text_that_saved(self, make_editor):
        editor, service = make_editor([_line("Original")])
        await editor.load()
        release_second = asyncio.Event()

        async def save(chronicle_id, line_id, **changes):
            if changes["text"] == "Second":
                await release_second.wait()
                raise RuntimeError("database is locked")

        service.update_line.side_effect = save
        await _edit_text(editor, "First")
        second = asyncio.create_task(_edit_text(editor, "Second"))
        await asyncio.sleep(0)
        release_second.set()
        await second

        assert _shown_text(_row(editor)) == "First"
        assert editor.ordered[0].text == "First"

    @pytest.mark.asyncio
    async def test_paging_saves_text_whose_blur_never_came(self, make_editor):
        """The Flet client sends no blur for a focused field it takes off the screen."""
        editor, service = make_editor(_long(WINDOW_SIZE + 1))
        await editor.load()
        field = await _open_text(editor)
        field.value = "Typed, never blurred"

        await _press(editor, editor.pager.next_button)

        service.update_line.assert_awaited_once()
        assert service.update_line.await_args.kwargs["text"] == "Typed, never blurred"
        assert editor.ordered[0].text == "Typed, never blurred"

    @pytest.mark.asyncio
    async def test_finishing_editing_saves_the_open_text(self, make_editor):
        editor, service = make_editor([_line("Old")])
        await editor.load()
        field = await _open_text(editor)
        field.value = "New"

        await editor.finish_editing()

        assert service.update_line.await_args.kwargs["text"] == "New"

    @pytest.mark.asyncio
    async def test_editing_does_not_reload_the_whole_list(self, make_editor):
        """Reloading on every save would throw away the scroll position."""
        editor, service = make_editor([_line("One")])
        await editor.load()
        service.get_transcript.reset_mock()

        await _edit_text(editor, "Two")

        service.get_transcript.assert_not_awaited()


class TestReassigningASpeaker:
    @pytest.mark.asyncio
    async def test_the_picker_opens_empty_with_the_speaker_as_a_hint(self, make_editor):
        """Typing filters at once, and the line's speaker never looks deleted."""
        editor, _ = make_editor([_line(speaker="Nyx")])
        await editor.load()

        picker = await _open_speaker(editor)

        assert picker.value is None
        assert picker.hint_text == "Nyx"
        assert picker.editable is True
        assert picker.enable_filter is True

    @pytest.mark.asyncio
    async def test_the_picker_offers_every_workspace_name(self, make_editor):
        editor, service = make_editor(speakers=["Alice", "Nyx", "Vale"])
        await editor.load()

        picker = await _open_speaker(editor)

        assert [option.key for option in picker.options] == ["Alice", "Nyx", "Vale"]
        service.speaker_suggestions.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_the_picker_replaces_only_the_speaker(self, make_editor):
        editor, _ = make_editor([_line("Hello there", speaker="Vale")])
        await editor.load()

        await _open_speaker(editor)

        texts = find_controls(_row(editor), lambda c: isinstance(c, ft.Text))
        assert texts[-1].spans[0].text == ": Hello there"

    @pytest.mark.asyncio
    async def test_picking_a_different_speaker_saves_it_and_closes(self, make_editor):
        editor, service = make_editor([_line(speaker="Nyx")])
        await editor.load()

        await _pick(editor, "Vale")

        assert service.update_line.await_args.kwargs["speaker_name"] == "Vale"
        assert editor.open is None
        assert _shown_speaker(_row(editor)) == "Vale: "

    @pytest.mark.asyncio
    async def test_the_line_takes_the_spelling_the_chronicle_keeps(self, make_editor):
        """Ticket 083: `vale` picked where `Vale` exists is stored, and shown, as `Vale`."""
        editor, service = make_editor([_line(speaker="Nyx")])
        service.update_line.return_value = _line(speaker="Vale")
        await editor.load()

        await _pick(editor, "vale")

        assert _shown_speaker(_row(editor)) == "Vale: "

    @pytest.mark.asyncio
    async def test_picking_the_same_speaker_saves_nothing(self, make_editor):
        editor, service = make_editor([_line(speaker="Nyx")])
        await editor.load()

        await _pick(editor, "Nyx")

        service.update_line.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_leaving_without_picking_saves_nothing_even_if_typed(self, make_editor):
        """A half-typed filter such as `Az` must never become a speaker."""
        editor, service = make_editor([_line(speaker="Nyx")])
        await editor.load()
        picker = await _open_speaker(editor)
        picker.text = "Az"

        with patch("chronicler.desktop.views.transcript.editor.PICKER_BLUR_GRACE", 0):
            await editor.speaker_blurred(MagicMock(control=picker))

        service.update_line.assert_not_awaited()
        assert editor.open is None
        assert _shown_speaker(_row(editor)) == "Nyx: "

    @pytest.mark.asyncio
    async def test_leaving_with_nothing_typed_keeps_the_picker_open(self, make_editor):
        """The picker's arrow blurs the field as it opens the menu."""
        editor, service = make_editor([_line(speaker="Nyx")])
        await editor.load()
        picker = await _open_speaker(editor)
        picker.text = ""

        with patch("chronicler.desktop.views.transcript.editor.PICKER_BLUR_GRACE", 0):
            await editor.speaker_blurred(MagicMock(control=picker))

        assert editor.open is not None
        service.update_line.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_picker_left_open_closes_when_another_line_is_clicked(self, make_editor):
        editor, service = make_editor([_line(speaker="Nyx"), _line("Next", start=1.0)])
        await editor.load()
        await _open_speaker(editor, 0)

        await _open_text(editor, 1)

        assert _shown_speaker(_row(editor, 0)) == "Nyx: "
        service.update_line.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_pick_arriving_just_after_the_blur_still_counts(self, make_editor):
        """Clicking an option can blur the field before the pick reaches us."""
        editor, service = make_editor([_line(speaker="Nyx")])
        await editor.load()
        picker = await _open_speaker(editor)

        with patch("chronicler.desktop.views.transcript.editor.PICKER_BLUR_GRACE", 0.05):
            blurring = asyncio.create_task(editor.speaker_blurred(MagicMock(control=picker)))
            await asyncio.sleep(0)
            picker.value = "Vale"
            await editor.speaker_picked(MagicMock(control=picker))
            await blurring

        assert service.update_line.await_args.kwargs["speaker_name"] == "Vale"
        assert _shown_speaker(_row(editor)) == "Vale: "

    @pytest.mark.asyncio
    async def test_escape_closes_the_picker(self, make_editor):
        editor, service = make_editor([_line(speaker="Nyx")])
        await editor.load()
        await _open_speaker(editor)

        await editor.key_pressed(MagicMock(key="Escape"))

        assert editor.open is None
        service.update_line.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_failed_speaker_save_puts_the_old_speaker_back(self, make_editor):
        editor, service = make_editor([_line(speaker="Nyx")])
        service.update_line.side_effect = RuntimeError("database is locked")
        await editor.load()

        await _pick(editor, "Vale")

        assert _shown_speaker(_row(editor)) == "Nyx: "
        assert editor.ordered[0].speaker_name == "Nyx"

    @pytest.mark.asyncio
    async def test_a_speaker_failing_after_paging_back_repaints_the_rebuilt_row(self, make_editor):
        editor, service = make_editor(_long(WINDOW_SIZE + 1))
        await editor.load()
        release = asyncio.Event()

        async def failing_save(*args, **kwargs):
            await release.wait()
            raise RuntimeError("database is locked")

        service.update_line.side_effect = failing_save

        saving = asyncio.create_task(_pick(editor, "Vale"))
        await asyncio.sleep(0)
        await _press(editor, editor.pager.next_button)
        await _press(editor, editor.pager.previous_button)
        release.set()
        await saving

        assert _shown_speaker(_row(editor)) == "Nyx: "
        assert editor.ordered[0].speaker_name == "Nyx"

    @pytest.mark.asyncio
    async def test_a_new_name_is_offered_by_the_next_picker(self, make_editor):
        editor, _ = make_editor([_line(), _line(start=1.0)])
        await editor.load()

        await _pick(editor, "Morrow", index=0)
        picker = await _open_speaker(editor, 1)

        assert "Morrow" in [option.key for option in picker.options]

    @pytest.mark.asyncio
    async def test_an_empty_pick_saves_nothing(self, make_editor):
        """A line with no speaker at all is not a state the editor should be able to make."""
        editor, service = make_editor([_line(speaker="Nyx")])
        await editor.load()

        await _pick(editor, "   ")

        service.update_line.assert_not_awaited()


class TestKeys:
    @pytest.mark.asyncio
    async def test_editing_listens_for_keys_and_finishing_hands_them_back(
        self, make_editor, attach_page
    ):
        editor, _ = make_editor()
        page = attach_page(TranscriptEditor)
        earlier = MagicMock()
        page.on_keyboard_event = earlier

        await editor.load()
        listening = page.on_keyboard_event
        await editor.finish_editing()

        assert listening == editor.key_pressed
        assert page.on_keyboard_event is earlier

    @pytest.mark.asyncio
    async def test_keys_with_nothing_open_go_to_the_earlier_handler(self, make_editor, attach_page):
        editor, _ = make_editor()
        page = attach_page(TranscriptEditor)
        earlier = MagicMock()
        page.on_keyboard_event = earlier
        await editor.load()

        event = MagicMock(key="Escape")
        await editor.key_pressed(event)

        earlier.assert_called_once_with(event)


class TestDeletingALine:
    @pytest.mark.asyncio
    async def test_it_confirms_first(self, make_editor, attach_page):
        editor, service = make_editor([_line("Doomed")])
        attach_page(TranscriptEditor)
        await editor.load()

        with patch(
            "chronicler.desktop.views.transcript.editor.confirm",
            new=AsyncMock(return_value=False),
        ) as ask:
            await editor.delete_clicked(MagicMock(control=_row(editor).delete_button))

        ask.assert_awaited_once()
        service.delete_line.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_confirming_deletes_and_reloads(self, make_editor, attach_page):
        editor, service = make_editor([_line("Doomed")])
        attach_page(TranscriptEditor)
        await editor.load()

        with patch(
            "chronicler.desktop.views.transcript.editor.confirm",
            new=AsyncMock(return_value=True),
        ):
            await editor.delete_clicked(MagicMock(control=_row(editor).delete_button))

        service.delete_line.assert_awaited_once()
        editor.on_changed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_text_open_in_another_row_is_saved_before_the_reload(
        self, make_editor, attach_page
    ):
        """The reload replaces every row, and a field taken off the screen sends no blur."""
        kept, doomed = _line("Kept", start=0.0), _line("Doomed", start=1.0)
        editor, service = make_editor([kept, doomed])
        attach_page(TranscriptEditor)
        await editor.load()
        field = await _open_text(editor, 0)
        field.value = "Kept, corrected"
        service.get_transcript.return_value = [kept]

        with patch(
            "chronicler.desktop.views.transcript.editor.confirm",
            new=AsyncMock(return_value=True),
        ):
            await editor.delete_clicked(MagicMock(control=_row(editor, 1).delete_button))

        service.update_line.assert_awaited_once()
        assert service.update_line.await_args.args[1] == kept.id
        assert _shown_text(_row(editor)) == "Kept, corrected"

    @pytest.mark.asyncio
    async def test_the_confirmation_quotes_the_line(self, make_editor, attach_page):
        editor, _ = make_editor([_line("The exact words at risk")])
        attach_page(TranscriptEditor)
        await editor.load()

        with patch(
            "chronicler.desktop.views.transcript.editor.confirm",
            new=AsyncMock(return_value=False),
        ) as ask:
            await editor.delete_clicked(MagicMock(control=_row(editor).delete_button))

        assert "The exact words" in " ".join(str(part) for part in ask.await_args[0])


class TestConcurrency:
    @pytest.mark.asyncio
    async def test_two_rows_edit_independently(self, make_editor):
        editor, service = make_editor([_line("First"), _line("Second", start=1.0)])
        await editor.load()

        await _edit_text(editor, "First edited", index=0)
        await _edit_text(editor, "Second edited", index=1)

        saved = {call.kwargs["text"] for call in service.update_line.await_args_list}
        assert saved == {"First edited", "Second edited"}


class TestDescribeTranscriptError:
    def test_a_chronicle_from_a_newer_chronicler_says_to_update(self):
        from chronicler.core.database_manager import NewerSchemaError
        from chronicler.desktop.views.transcript.editor import describe_transcript_error

        message = describe_transcript_error(NewerSchemaError("project"))

        assert "newer version" in message
        assert "Update Chronicler" in message

    def test_any_other_error_is_shown_as_it_is(self):
        from chronicler.desktop.views.transcript.editor import describe_transcript_error

        assert "disk on fire" in describe_transcript_error(OSError("disk on fire"))
