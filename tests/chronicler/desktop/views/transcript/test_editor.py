"""Tests for the per-line transcript editor."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import flet as ft
import pytest

from chronicler.core.models import Chronicle, TranscriptLine
from chronicler.desktop.theme import theme_colors
from chronicler.desktop.views.transcript.editor import WINDOW_SIZE, TranscriptEditor
from chronicler.i18n import set_locale


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


def _row(editor, index=0):
    return editor.line_list.controls[index]


def _fields(row) -> dict:
    return {c.data.split(":")[0]: c for c in row.controls if getattr(c, "data", None)}


class TestLoading:
    @pytest.mark.asyncio
    async def test_one_row_per_line(self, make_editor):
        editor, _ = make_editor([_line("First"), _line("Second", start=1.0)])

        await editor.load()

        assert len(editor.line_list.controls) == 2

    @pytest.mark.asyncio
    async def test_each_row_shows_its_text_and_speaker(self, make_editor):
        editor, _ = make_editor([_line("Hello there", speaker="Vale")])

        await editor.load()

        fields = _fields(_row(editor))
        assert fields["text"].value == "Hello there"
        assert fields["speaker"].value == "Vale"

    @pytest.mark.asyncio
    async def test_an_empty_transcript_says_so(self, make_editor):
        editor, _ = make_editor([])

        await editor.load()

        assert len(editor.line_list.controls) == 1
        assert isinstance(editor.line_list.controls[0], ft.Text)

    @pytest.mark.asyncio
    async def test_the_speaker_field_offers_every_workspace_name(self, make_editor):
        editor, service = make_editor(speakers=["Alice", "Nyx", "Vale"])

        await editor.load()

        options = [option.key for option in _fields(_row(editor))["speaker"].options]
        assert options == ["Alice", "Nyx", "Vale"]
        service.speaker_suggestions.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_the_speaker_field_accepts_a_new_name(self, make_editor):
        editor, _ = make_editor()

        await editor.load()

        assert _fields(_row(editor))["speaker"].editable is True

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


def _long(count):
    return [_line(f"Line {i}", start=float(i)) for i in range(count)]


def _texts(editor) -> list[str]:
    return [_fields(row)["text"].value for row in editor.line_list.controls]


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

        assert len(editor.line_list.controls) == WINDOW_SIZE
        assert _texts(editor)[0] == "Line 0"
        assert editor.pager.visible is True
        assert "1-100" in editor.window_label.value
        assert "1,686" in editor.window_label.value

    @pytest.mark.asyncio
    async def test_the_line_count_is_written_the_local_way(self, make_editor):
        editor, _ = make_editor(_long(1686))
        set_locale("de")
        try:
            await editor.load()
        finally:
            set_locale("en")

        assert "1.686" in editor.window_label.value

    @pytest.mark.asyncio
    async def test_next_and_previous_move_one_window(self, make_editor):
        editor, _ = make_editor(_long(250))
        await editor.load()

        await _press(editor, editor.next_button)
        assert _texts(editor)[0] == f"Line {WINDOW_SIZE}"

        await _press(editor, editor.previous_button)
        assert _texts(editor)[0] == "Line 0"

    @pytest.mark.asyncio
    async def test_last_shows_the_remainder_and_first_goes_back(self, make_editor):
        editor, _ = make_editor(_long(250))
        await editor.load()

        await _press(editor, editor.last_button)
        assert _texts(editor) == [f"Line {i}" for i in range(200, 250)]
        assert "201-250" in editor.window_label.value

        await _press(editor, editor.first_button)
        assert _texts(editor)[0] == "Line 0"

    @pytest.mark.asyncio
    async def test_buttons_that_lead_nowhere_are_disabled(self, make_editor):
        editor, _ = make_editor(_long(250))
        await editor.load()

        assert editor.first_button.disabled and editor.previous_button.disabled
        assert not editor.next_button.disabled

        await _press(editor, editor.last_button)

        assert editor.next_button.disabled and editor.last_button.disabled
        assert not editor.previous_button.disabled

    @pytest.mark.asyncio
    async def test_a_line_on_a_later_window_still_saves(self, make_editor):
        editor, service = make_editor(_long(250))
        await editor.load()
        await _press(editor, editor.next_button)
        field = _fields(_row(editor))["text"]
        field.value = "Corrected"

        await editor.text_blurred(MagicMock(control=field))

        assert service.update_line.await_args.kwargs["text"] == "Corrected"

    @pytest.mark.asyncio
    async def test_deleting_keeps_the_window_that_was_showing(self, make_editor, attach_page):
        lines = _long(250)
        editor, service = make_editor(lines)
        attach_page(TranscriptEditor)
        await editor.load()
        await _press(editor, editor.next_button)
        button = _fields(_row(editor))["delete"]
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
        await _press(editor, editor.last_button)
        service.get_transcript.return_value = lines[:100]

        await editor.load()

        assert _texts(editor)[0] == "Line 0"
        assert editor.pager.visible is False


class TestEditingText:
    @pytest.mark.asyncio
    async def test_a_changed_line_is_saved(self, make_editor):
        editor, service = make_editor([_line("原文")])
        await editor.load()
        field = _fields(_row(editor))["text"]
        field.value = "Corrected"

        await editor.text_blurred(MagicMock(control=field))

        service.update_line.assert_awaited_once()
        assert service.update_line.await_args.kwargs["text"] == "Corrected"

    @pytest.mark.asyncio
    async def test_an_unchanged_line_saves_nothing(self, make_editor):
        """Blur fires on every focus change, edited or not - same rule as Settings."""
        editor, service = make_editor([_line("Untouched")])
        await editor.load()

        await editor.text_blurred(MagicMock(control=_fields(_row(editor))["text"]))

        service.update_line.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_second_edit_compares_against_the_first(self, make_editor):
        editor, service = make_editor([_line("One")])
        await editor.load()
        field = _fields(_row(editor))["text"]

        field.value = "Two"
        await editor.text_blurred(MagicMock(control=field))
        await editor.text_blurred(MagicMock(control=field))

        assert service.update_line.await_count == 1

    @pytest.mark.asyncio
    async def test_a_failed_save_is_reported_and_the_field_reverts(self, make_editor):
        editor, service = make_editor([_line("Original")])
        service.update_line.side_effect = RuntimeError("database is locked")
        await editor.load()
        field = _fields(_row(editor))["text"]
        field.value = "Attempted"

        await editor.text_blurred(MagicMock(control=field))

        editor.show_snackbar.assert_called_once()
        assert "database is locked" in editor.show_snackbar.call_args[0][0]
        assert field.value == "Original"

    @pytest.mark.asyncio
    async def test_paging_back_during_a_save_shows_the_new_text(self, make_editor):
        """
        Paging away blurs the field and starts the save; paging straight back rebuilds
        the row. Built from the old text, it would save the old text over the new one.
        """
        editor, service = make_editor(_long(WINDOW_SIZE + 1))
        await editor.load()
        release = asyncio.Event()

        async def slow_save(*args, **kwargs):
            await release.wait()

        service.update_line.side_effect = slow_save
        field = _fields(_row(editor))["text"]
        field.value = "Corrected"

        saving = asyncio.create_task(editor.text_blurred(MagicMock(control=field)))
        await asyncio.sleep(0)
        await _press(editor, editor.next_button)
        await _press(editor, editor.previous_button)
        rebuilt = _fields(_row(editor))["text"]
        release.set()
        await saving

        assert rebuilt.value == "Corrected"
        await editor.text_blurred(MagicMock(control=rebuilt))
        assert service.update_line.await_count == 1

    @pytest.mark.asyncio
    async def test_a_failed_save_puts_the_old_text_back_on_the_line(self, make_editor):
        editor, service = make_editor(_long(WINDOW_SIZE + 1))
        service.update_line.side_effect = RuntimeError("database is locked")
        await editor.load()
        field = _fields(_row(editor))["text"]
        field.value = "Attempted"

        await editor.text_blurred(MagicMock(control=field))
        await _press(editor, editor.next_button)
        await _press(editor, editor.previous_button)

        assert _fields(_row(editor))["text"].value == "Line 0"

    @pytest.mark.asyncio
    async def test_editing_does_not_reload_the_whole_list(self, make_editor):
        """Reloading on every blur would throw away the caret and the scroll position."""
        editor, service = make_editor([_line("One")])
        await editor.load()
        service.get_transcript.reset_mock()
        field = _fields(_row(editor))["text"]
        field.value = "Two"

        await editor.text_blurred(MagicMock(control=field))

        service.get_transcript.assert_not_awaited()


class TestReassigningASpeaker:
    @pytest.mark.asyncio
    async def test_choosing_a_different_speaker_saves_it(self, make_editor):
        editor, service = make_editor([_line(speaker="Nyx")])
        await editor.load()
        field = _fields(_row(editor))["speaker"]
        field.value = "Vale"

        await editor.speaker_changed(MagicMock(control=field))

        assert service.update_line.await_args.kwargs["speaker_name"] == "Vale"

    @pytest.mark.asyncio
    async def test_reselecting_the_same_speaker_saves_nothing(self, make_editor):
        editor, service = make_editor([_line(speaker="Nyx")])
        await editor.load()

        await editor.speaker_changed(MagicMock(control=_fields(_row(editor))["speaker"]))

        service.update_line.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_failed_speaker_save_puts_the_old_speaker_back(self, make_editor):
        editor, service = make_editor([_line(speaker="Nyx")])
        service.update_line.side_effect = RuntimeError("database is locked")
        await editor.load()
        field = _fields(_row(editor))["speaker"]
        field.value = "Vale"

        await editor.speaker_changed(MagicMock(control=field))

        assert field.value == "Nyx"
        assert editor.lines[_fields(_row(editor))["speaker"].data.split(":")[1]].speaker_name == (
            "Nyx"
        )

    @pytest.mark.asyncio
    async def test_a_new_name_is_offered_on_the_next_window(self, make_editor):
        editor, _ = make_editor(_long(WINDOW_SIZE + 1))
        await editor.load()
        first = _fields(_row(editor, 0))["speaker"]
        first.value = "Morrow"

        await editor.speaker_changed(MagicMock(control=first))
        await _press(editor, editor.next_button)

        options = [option.key for option in _fields(_row(editor))["speaker"].options]
        assert "Morrow" in options

    @pytest.mark.asyncio
    async def test_clearing_the_speaker_saves_nothing(self, make_editor):
        """A line with no speaker at all is not a state the editor should be able to make."""
        editor, service = make_editor([_line(speaker="Nyx")])
        await editor.load()
        field = _fields(_row(editor))["speaker"]
        field.value = "   "

        await editor.speaker_changed(MagicMock(control=field))

        service.update_line.assert_not_awaited()


class TestDeletingALine:
    @pytest.mark.asyncio
    async def test_it_confirms_first(self, make_editor, attach_page):
        editor, service = make_editor([_line("Doomed")])
        attach_page(TranscriptEditor)
        await editor.load()
        button = _fields(_row(editor))["delete"]

        with patch(
            "chronicler.desktop.views.transcript.editor.confirm",
            new=AsyncMock(return_value=False),
        ) as ask:
            await editor.delete_clicked(MagicMock(control=button))

        ask.assert_awaited_once()
        service.delete_line.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_confirming_deletes_and_reloads(self, make_editor, attach_page):
        editor, service = make_editor([_line("Doomed")])
        attach_page(TranscriptEditor)
        await editor.load()
        button = _fields(_row(editor))["delete"]

        with patch(
            "chronicler.desktop.views.transcript.editor.confirm",
            new=AsyncMock(return_value=True),
        ):
            await editor.delete_clicked(MagicMock(control=button))

        service.delete_line.assert_awaited_once()
        editor.on_changed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_the_confirmation_quotes_the_line(self, make_editor, attach_page):
        editor, _ = make_editor([_line("The exact words at risk")])
        attach_page(TranscriptEditor)
        await editor.load()
        button = _fields(_row(editor))["delete"]

        with patch(
            "chronicler.desktop.views.transcript.editor.confirm",
            new=AsyncMock(return_value=False),
        ) as ask:
            await editor.delete_clicked(MagicMock(control=button))

        assert "The exact words" in " ".join(str(part) for part in ask.await_args[0])


class TestTimestamps:
    @pytest.mark.asyncio
    async def test_each_row_shows_when_the_line_starts(self, make_editor):
        editor, _ = make_editor([_line("Later", start=3725.0)])

        await editor.load()

        stamps = [c.value for c in _row(editor).controls if isinstance(c, ft.Text)]
        assert any("01:02:05" in value for value in stamps)


class TestConcurrency:
    @pytest.mark.asyncio
    async def test_two_rows_edit_independently(self, make_editor):
        editor, service = make_editor([_line("First"), _line("Second", start=1.0)])
        await editor.load()

        first = _fields(_row(editor, 0))["text"]
        second = _fields(_row(editor, 1))["text"]
        first.value = "First edited"
        second.value = "Second edited"

        await asyncio.gather(
            editor.text_blurred(MagicMock(control=first)),
            editor.text_blurred(MagicMock(control=second)),
        )

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
