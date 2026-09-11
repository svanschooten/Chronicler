"""Tests for the one dialog that starts a transcription."""

import asyncio
from unittest.mock import MagicMock

import flet as ft
import pytest

from chronicler.core.config import Settings
from chronicler.core.models import AudioSource
from chronicler.desktop.views.transcript.transcribe_dialog import (
    TranscribeChoice,
    TranscribeDialog,
)


def _source(**overrides):
    overrides.setdefault("filename", "alice.mp3")
    return AudioSource(**overrides)


@pytest.fixture
def ask(isolated_config):
    """
    Opens the dialog, returning (task, dialog, subject) with it awaiting a click.

    `isolated_config` keeps the defaults away from the developer's own settings file.
    """

    async def _ask(source=None, speakers=None, settings=None):
        page = MagicMock(spec=ft.Page)
        dialog_under_test = TranscribeDialog(
            source or _source(),
            speakers if speakers is not None else ["Alice", "Bob"],
            settings or Settings(),
        )
        task = asyncio.ensure_future(dialog_under_test.ask(page))
        await asyncio.sleep(0)
        (dialog,), _ = page.show_dialog.call_args
        return task, dialog, dialog_under_test

    return _ask


def _fields(dialog) -> dict[str, object]:
    return {control.data: control for control in dialog.content.controls if control.data}


class TestDefaults:
    @pytest.mark.asyncio
    async def test_the_language_starts_at_the_configured_default(self, ask):
        settings = Settings()
        settings.transcription.language = "nl"
        task, dialog, _ = await ask(settings=settings)

        assert _fields(dialog)["language"].value == "nl"

        await dialog.actions[0].on_click(MagicMock())
        await asyncio.wait_for(task, timeout=1)

    @pytest.mark.asyncio
    async def test_an_unset_language_starts_at_auto(self, ask):
        task, dialog, _ = await ask()

        assert _fields(dialog)["language"].value == "auto"

        await dialog.actions[0].on_click(MagicMock())
        await asyncio.wait_for(task, timeout=1)

    @pytest.mark.asyncio
    async def test_auto_is_the_first_language_option(self, ask):
        task, dialog, _ = await ask()

        assert [option.key for option in _fields(dialog)["language"].options][0] == "auto"

        await dialog.actions[0].on_click(MagicMock())
        await asyncio.wait_for(task, timeout=1)

    @pytest.mark.asyncio
    async def test_the_model_starts_at_the_configured_default(self, ask):
        settings = Settings()
        settings.transcription.model_size = "small"
        task, dialog, _ = await ask(settings=settings)

        assert _fields(dialog)["model_size"].value == "small"

        await dialog.actions[0].on_click(MagicMock())
        await asyncio.wait_for(task, timeout=1)

    @pytest.mark.asyncio
    async def test_the_threshold_starts_at_the_configured_default(self, ask):
        settings = Settings()
        settings.transcription.no_speech_threshold = 0.45
        task, dialog, _ = await ask(settings=settings)

        assert _fields(dialog)["no_speech_threshold"].value == "0.45"

        await dialog.actions[0].on_click(MagicMock())
        await asyncio.wait_for(task, timeout=1)

    @pytest.mark.asyncio
    async def test_normalize_first_starts_at_the_configured_default(self, ask):
        settings = Settings()
        settings.transcription.normalize_first = True
        task, dialog, _ = await ask(settings=settings)

        assert _fields(dialog)["normalize_first"].value is True

        await dialog.actions[0].on_click(MagicMock())
        await asyncio.wait_for(task, timeout=1)

    @pytest.mark.asyncio
    async def test_an_already_normalized_source_offers_no_normalize_toggle(self, ask):
        source = _source(normalized_filename="alice.normalized.wav", content_hash="h")
        source.normalization_state = "DONE"
        source.normalized_hash = "h"
        task, dialog, _ = await ask(source=source)

        assert "normalize_first" not in _fields(dialog)

        await dialog.actions[0].on_click(MagicMock())
        await asyncio.wait_for(task, timeout=1)

    @pytest.mark.asyncio
    async def test_the_current_speaker_is_preselected(self, ask):
        task, dialog, _ = await ask(source=_source(speaker_name="Bob"))

        assert _fields(dialog)["speaker"].value == "Bob"

        await dialog.actions[0].on_click(MagicMock())
        await asyncio.wait_for(task, timeout=1)

    @pytest.mark.asyncio
    async def test_it_offers_every_known_speaker(self, ask):
        task, dialog, _ = await ask(speakers=["Alice", "Bob", "Carol"])

        options = [option.key for option in _fields(dialog)["speaker"].options]
        assert options == ["Alice", "Bob", "Carol"]

        await dialog.actions[0].on_click(MagicMock())
        await asyncio.wait_for(task, timeout=1)

    @pytest.mark.asyncio
    async def test_the_speaker_field_can_be_typed_into(self, ask):
        task, dialog, _ = await ask()

        speaker = _fields(dialog)["speaker"]
        assert speaker.editable is True
        assert speaker.enable_filter is True

        await dialog.actions[0].on_click(MagicMock())
        await asyncio.wait_for(task, timeout=1)


class TestStartingATranscription:
    @pytest.mark.asyncio
    async def test_it_returns_everything_the_task_needs(self, ask):
        task, dialog, _ = await ask()
        fields = _fields(dialog)
        fields["speaker"].value = "Alice"
        fields["language"].value = "de"
        fields["model_size"].value = "medium"
        fields["no_speech_threshold"].value = "0.4"
        fields["normalize_first"].value = True

        await dialog.actions[2].on_click(MagicMock())
        choice = await asyncio.wait_for(task, timeout=1)

        assert choice == TranscribeChoice(
            speaker="Alice",
            language="de",
            model_size="medium",
            no_speech_threshold=0.4,
            normalize_first=True,
            transcribe=True,
        )

    @pytest.mark.asyncio
    async def test_a_typed_name_is_used(self, ask):
        task, dialog, _ = await ask()
        _fields(dialog)["speaker"].value = "  Dave  "

        await dialog.actions[2].on_click(MagicMock())
        choice = await asyncio.wait_for(task, timeout=1)

        assert choice.speaker == "Dave"

    @pytest.mark.asyncio
    async def test_a_name_typed_into_the_dropdown_is_used(self, ask):
        """
        An editable Dropdown keeps the typed text and the selected option apart. A speaker
        who is not in the list yet only ever reaches `text`, so reading `value` alone
        dropped every newly introduced name and refused to start.
        """
        task, dialog, _ = await ask()
        _fields(dialog)["speaker"].text = "  Dave  "

        await dialog.actions[2].on_click(MagicMock())
        choice = await asyncio.wait_for(task, timeout=1)

        assert choice.speaker == "Dave"

    @pytest.mark.asyncio
    async def test_a_typed_name_wins_over_the_preselected_one(self, ask):
        """
        `value` holds the option last *selected*, so typing over a speaker the track
        already remembers leaves it on the old name. Preferring it would quietly transcribe
        as the wrong person.
        """
        task, dialog, _ = await ask(source=_source(speaker_name="Bob"))
        speaker = _fields(dialog)["speaker"]
        speaker.text = "Dave"

        await dialog.actions[2].on_click(MagicMock())
        choice = await asyncio.wait_for(task, timeout=1)

        assert speaker.value == "Bob", "the stale value is exactly what must not be used"
        assert choice.speaker == "Dave"

    @pytest.mark.asyncio
    async def test_the_remembered_name_is_used_before_the_field_reports_itself(self, ask):
        """
        The client fills `text` in from the selected option only once the dialog has
        mounted. Starting inside that window - open, click, done - has to use the
        remembered name rather than refuse for an empty field.
        """
        task, dialog, _ = await ask(source=_source(speaker_name="Bob"))
        assert _fields(dialog)["speaker"].text is None, "nothing has reported the field yet"

        await dialog.actions[2].on_click(MagicMock())
        choice = await asyncio.wait_for(task, timeout=1)

        assert choice.speaker == "Bob"

    @pytest.mark.asyncio
    async def test_the_field_emptied_for_filtering_falls_back_to_the_remembered_name(self, ask):
        """
        The picker empties itself on focus so typing filters from scratch, so an empty
        field no longer means "no speaker" - it usually means the user looked at the list
        and changed nothing. The name they can see is the one that gets used.
        """
        task, dialog, _ = await ask(source=_source(speaker_name="Bob"))
        speaker = _fields(dialog)["speaker"]
        speaker.on_focus(MagicMock(control=speaker))
        speaker.text = ""
        speaker.on_blur(MagicMock(control=speaker))

        await dialog.actions[2].on_click(MagicMock())
        choice = await asyncio.wait_for(task, timeout=1)

        assert choice.speaker == "Bob"

    @pytest.mark.asyncio
    async def test_a_track_with_no_speaker_yet_is_still_refused(self, ask):
        """The fallback only reaches for a name that exists; nothing is still nothing."""
        task, dialog, _ = await ask(source=_source())
        speaker = _fields(dialog)["speaker"]
        speaker.text = ""

        await dialog.actions[2].on_click(MagicMock())
        await asyncio.sleep(0)

        assert not task.done()
        assert speaker.error_text

        await dialog.actions[0].on_click(MagicMock())
        await asyncio.wait_for(task, timeout=1)

    @pytest.mark.asyncio
    async def test_starting_without_a_speaker_is_refused_rather_than_queued(self, ask):
        task, dialog, subject = await ask()

        await dialog.actions[2].on_click(MagicMock())
        await asyncio.sleep(0)

        assert not task.done()
        assert _fields(dialog)["speaker"].error_text

        await dialog.actions[0].on_click(MagicMock())
        await asyncio.wait_for(task, timeout=1)

    @pytest.mark.asyncio
    async def test_an_unusable_threshold_is_refused(self, ask):
        task, dialog, _ = await ask()
        fields = _fields(dialog)
        fields["speaker"].value = "Alice"
        fields["no_speech_threshold"].value = "banana"

        await dialog.actions[2].on_click(MagicMock())
        await asyncio.sleep(0)

        assert not task.done()
        assert fields["no_speech_threshold"].error

        await dialog.actions[0].on_click(MagicMock())
        await asyncio.wait_for(task, timeout=1)


class TestSavingTheSpeakerOnly:
    @pytest.mark.asyncio
    async def test_it_returns_the_speaker_without_asking_to_transcribe(self, ask):
        task, dialog, _ = await ask()
        _fields(dialog)["speaker"].value = "Alice"

        await dialog.actions[1].on_click(MagicMock())
        choice = await asyncio.wait_for(task, timeout=1)

        assert choice.speaker == "Alice"
        assert choice.transcribe is False

    @pytest.mark.asyncio
    async def test_it_still_needs_a_speaker(self, ask):
        task, dialog, _ = await ask()

        await dialog.actions[1].on_click(MagicMock())
        await asyncio.sleep(0)

        assert not task.done()

        await dialog.actions[0].on_click(MagicMock())
        await asyncio.wait_for(task, timeout=1)


class TestWithNoKnownSpeakers:
    """
    The first track in a chronicle has nobody to pick from, and an editable Dropdown with
    zero options is a menu that cannot be opened, so the field becomes a plain TextField.
    """

    @pytest.mark.asyncio
    async def test_the_speaker_field_is_a_plain_text_field(self, ask):
        task, dialog, _ = await ask(speakers=[])

        assert isinstance(_fields(dialog)["speaker"], ft.TextField)

        await dialog.actions[0].on_click(MagicMock())
        await asyncio.wait_for(task, timeout=1)

    @pytest.mark.asyncio
    async def test_a_typed_name_starts_the_transcription(self, ask):
        task, dialog, _ = await ask(speakers=[])
        _fields(dialog)["speaker"].value = "  Dave  "

        await dialog.actions[2].on_click(MagicMock())
        choice = await asyncio.wait_for(task, timeout=1)

        assert choice.speaker == "Dave"

    @pytest.mark.asyncio
    async def test_a_remembered_speaker_still_prefills_the_field(self, ask):
        task, dialog, _ = await ask(speakers=[], source=_source(speaker_name="Bob"))

        assert _fields(dialog)["speaker"].value == "Bob"

        await dialog.actions[0].on_click(MagicMock())
        await asyncio.wait_for(task, timeout=1)

    @pytest.mark.asyncio
    async def test_the_missing_speaker_message_lands_where_it_renders(self, ask):
        """
        A TextField renders `error` and a Dropdown renders `error_text`. Both are plain
        dataclasses that accept the other spelling without complaint, so putting it on the
        wrong one loses the message with nothing raised to say so.
        """
        task, dialog, _ = await ask(speakers=[])

        await dialog.actions[2].on_click(MagicMock())
        await asyncio.sleep(0)

        assert not task.done()
        field = _fields(dialog)["speaker"]
        assert field.error, "a TextField renders `error`"
        assert not getattr(field, "error_text", None), "`error_text` here would be silent"

        await dialog.actions[0].on_click(MagicMock())
        await asyncio.wait_for(task, timeout=1)


class TestCancelling:
    @pytest.mark.asyncio
    async def test_it_returns_nothing(self, ask):
        task, dialog, _ = await ask()

        await dialog.actions[0].on_click(MagicMock())

        assert await asyncio.wait_for(task, timeout=1) is None


class TestLabelling:
    @pytest.mark.asyncio
    async def test_the_title_names_the_track(self, ask):
        task, dialog, _ = await ask(source=_source(filename="gm-track.mp3"))

        assert "gm-track.mp3" in dialog.title.value

        await dialog.actions[0].on_click(MagicMock())
        await asyncio.wait_for(task, timeout=1)

    @pytest.mark.asyncio
    async def test_an_already_transcribed_track_offers_to_redo_it(self, ask):
        source = _source(content_hash="h", transcribed_hash="h")
        source.transcription_state = "DONE"
        task, dialog, _ = await ask(source=source)

        assert "again" in dialog.actions[2].content.lower()

        await dialog.actions[0].on_click(MagicMock())
        await asyncio.wait_for(task, timeout=1)
