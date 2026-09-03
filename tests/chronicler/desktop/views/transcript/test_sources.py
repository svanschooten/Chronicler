"""Tests for the Sources panel - a chronicle's audio tracks and the actions on them."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from chronicler.core.models import AudioSource, Chronicle, SourceState
from chronicler.desktop.theme import theme_colors
from chronicler.desktop.views.transcript.sources import SourcesPanel
from chronicler.desktop.views.transcript.transcribe_dialog import TranscribeChoice


def _choice(**overrides):
    values = {
        "speaker": "Alice",
        "language": "auto",
        "model_size": "base",
        "no_speech_threshold": 0.6,
        "normalize_first": False,
        "transcribe": True,
    }
    values.update(overrides)
    return TranscribeChoice(**values)


def source(filename="alice.mp3", **overrides):
    overrides.setdefault("path", f"/s/{filename}")
    return AudioSource(filename=filename, content_hash="h", **overrides)


@pytest.fixture
def make_panel():
    def _make(transcript_service=None, task_service=None, chronicle=None):
        panel = SourcesPanel(
            chronicle or Chronicle(title="Some Chronicle"),
            transcript_service or AsyncMock(),
            task_service or AsyncMock(),
            theme_colors(True),
            MagicMock(),
        )
        panel.source_list.update = MagicMock()
        return panel

    return _make


@pytest.fixture
def panel_with(make_panel):
    def _make(sources, speakers=None):
        transcript_service = AsyncMock()
        transcript_service.list_audio_sources.return_value = sources
        transcript_service.speaker_suggestions.return_value = speakers or []
        return make_panel(transcript_service=transcript_service), transcript_service

    return _make


class TestLoading:
    @pytest.mark.asyncio
    async def test_shows_a_placeholder_when_there_are_no_sources(self, panel_with):
        panel, _ = panel_with([])

        await panel.load()

        assert len(panel.source_list.controls) == 1
        assert "No audio sources" in panel.source_list.controls[0].value

    @pytest.mark.asyncio
    async def test_lists_one_row_per_source_labelled_by_filename(self, panel_with):
        panel, _ = panel_with([source("alice.mp3"), source("bob.mp3")])

        await panel.load()

        assert [row.controls[0].controls[0].value for row in panel.source_list.controls] == [
            "alice.mp3",
            "bob.mp3",
        ]

    @pytest.mark.asyncio
    async def test_rows_carry_their_filename_for_the_action_handlers(self, panel_with):
        panel, _ = panel_with([source("alice.mp3")])

        await panel.load()

        actions = panel.source_list.controls[0].controls[1:]
        assert all(action.data == "alice.mp3" for action in actions)

    @pytest.mark.asyncio
    async def test_degrades_to_the_empty_state_when_listing_fails(self, make_panel):
        transcript_service = AsyncMock()
        transcript_service.list_audio_sources.side_effect = RuntimeError("no such directory")
        panel = make_panel(transcript_service=transcript_service)

        await panel.load()

        assert "No audio sources" in panel.source_list.controls[0].value

    @pytest.mark.asyncio
    async def test_refresh_reloads(self, panel_with):
        panel, transcript_service = panel_with([])

        await panel.refresh_clicked(MagicMock())

        transcript_service.list_audio_sources.assert_awaited_once()


class TestRowStatus:
    @pytest.mark.asyncio
    async def test_an_untranscribed_source_shows_its_speaker_placeholder(self, panel_with):
        panel, _ = panel_with([source()])

        await panel.load()

        assert "No speaker" in panel.source_list.controls[0].controls[0].controls[1].value

    @pytest.mark.asyncio
    async def test_an_assigned_speaker_is_shown(self, panel_with):
        panel, _ = panel_with([source(speaker_name="Alice")])

        await panel.load()

        assert "Alice" in panel.source_list.controls[0].controls[0].controls[1].value

    @pytest.mark.asyncio
    async def test_a_transcribed_source_is_marked_done(self, panel_with):
        panel, _ = panel_with(
            [
                source(
                    speaker_name="Alice",
                    transcription_state=SourceState.DONE,
                    transcribed_hash="h",
                )
            ]
        )

        await panel.load()

        assert "Transcribed" in panel.source_list.controls[0].controls[0].controls[1].value

    @pytest.mark.asyncio
    async def test_a_stale_transcription_is_not_marked_done(self, panel_with):
        panel, _ = panel_with(
            [source(transcription_state=SourceState.DONE, transcribed_hash="different")]
        )

        await panel.load()

        assert "Transcribed" not in panel.source_list.controls[0].controls[0].controls[1].value

    @pytest.mark.asyncio
    async def test_a_failed_source_shows_its_error(self, panel_with):
        panel, _ = panel_with(
            [source(transcription_state=SourceState.FAILED, transcription_error="model exploded")]
        )

        await panel.load()

        assert "model exploded" in panel.source_list.controls[0].controls[0].controls[1].value

    @pytest.mark.asyncio
    async def test_a_missing_file_is_flagged(self, panel_with):
        panel, _ = panel_with([source(missing=True)])

        await panel.load()

        assert "Missing" in panel.source_list.controls[0].controls[0].controls[1].value


class TestTheRowActions:
    @pytest.mark.asyncio
    async def test_a_row_offers_exactly_one_transcribe_action(self, panel_with):
        panel, _ = panel_with([source(speaker_name="Alice")])

        await panel.load()

        actions = panel.source_list.controls[0].controls[1:]
        assert [action.on_click for action in actions].count(panel.transcribe_source_clicked) == 1

    @pytest.mark.asyncio
    async def test_there_is_no_separate_assign_speaker_button(self, panel_with):
        panel, _ = panel_with([source()])

        await panel.load()

        tooltips = [c.tooltip for c in panel.source_list.controls[0].controls[1:]]
        assert not any("speaker" in (tooltip or "").lower() for tooltip in tooltips)

    @pytest.mark.asyncio
    async def test_an_untranscribed_track_says_transcribe(self, panel_with):
        panel, _ = panel_with([source()])

        await panel.load()

        tooltips = [c.tooltip for c in panel.source_list.controls[0].controls[1:]]
        assert "Start transcription" in tooltips

    @pytest.mark.asyncio
    async def test_a_transcribed_track_offers_to_redo_it(self, panel_with):
        panel, _ = panel_with([source(transcription_state=SourceState.DONE, transcribed_hash="h")])

        await panel.load()

        tooltips = [c.tooltip for c in panel.source_list.controls[0].controls[1:]]
        assert "Transcribe again" in tooltips

    @pytest.mark.asyncio
    async def test_the_full_filename_is_available_on_hover(self, panel_with):
        panel, _ = panel_with([source("a-very-long-session-filename.mp3")])

        await panel.load()

        assert (
            panel.source_list.controls[0].controls[0].tooltip == "a-very-long-session-filename.mp3"
        )


class TestTranscribing:
    @pytest.mark.asyncio
    async def test_it_always_opens_the_dialog_even_with_a_speaker_already_assigned(
        self, make_panel
    ):
        """The button says transcribe, so language and normalization are still choosable."""
        transcript_service = AsyncMock()
        transcript_service.list_audio_sources.return_value = [source(speaker_name="Alice")]
        panel = make_panel(transcript_service=transcript_service)
        panel._ask_transcribe = AsyncMock(return_value=None)
        await panel.load()

        await panel.transcribe_source_clicked(MagicMock(control=MagicMock(data="alice.mp3")))

        panel._ask_transcribe.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_it_passes_every_chosen_parameter_to_the_task(self, make_panel):
        transcript_service = AsyncMock()
        transcript_service.list_audio_sources.return_value = [source()]
        task_service = AsyncMock()
        panel = make_panel(transcript_service=transcript_service, task_service=task_service)
        panel._ask_transcribe = AsyncMock(
            return_value=TranscribeChoice(
                speaker="Carol",
                language="de",
                model_size="medium",
                no_speech_threshold=0.4,
                normalize_first=True,
                transcribe=True,
            )
        )
        await panel.load()

        await panel.transcribe_source_clicked(MagicMock(control=MagicMock(data="alice.mp3")))

        call = task_service.queue_transcribe.await_args
        assert call.args[1:] == ("/s/alice.mp3", "Carol")
        assert call.kwargs == {
            "language": "de",
            "model_size": "medium",
            "no_speech_threshold": 0.4,
            "normalize_first": True,
        }

    @pytest.mark.asyncio
    async def test_it_assigns_the_speaker_before_queueing(self, make_panel):
        transcript_service = AsyncMock()
        transcript_service.list_audio_sources.return_value = [source()]
        panel = make_panel(transcript_service=transcript_service)
        panel._ask_transcribe = AsyncMock(return_value=_choice(speaker="Carol"))
        await panel.load()

        await panel.transcribe_source_clicked(MagicMock(control=MagicMock(data="alice.mp3")))

        transcript_service.assign_speaker.assert_awaited_once_with(
            panel.chronicle.id, "alice.mp3", "Carol"
        )

    @pytest.mark.asyncio
    async def test_saving_the_speaker_alone_queues_nothing(self, make_panel):
        transcript_service = AsyncMock()
        transcript_service.list_audio_sources.return_value = [source()]
        task_service = AsyncMock()
        panel = make_panel(transcript_service=transcript_service, task_service=task_service)
        panel._ask_transcribe = AsyncMock(return_value=_choice(speaker="Dave", transcribe=False))
        await panel.load()

        await panel.transcribe_source_clicked(MagicMock(control=MagicMock(data="alice.mp3")))

        transcript_service.assign_speaker.assert_awaited_once_with(
            panel.chronicle.id, "alice.mp3", "Dave"
        )
        task_service.queue_transcribe.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cancelling_changes_nothing(self, make_panel):
        transcript_service = AsyncMock()
        transcript_service.list_audio_sources.return_value = [source()]
        task_service = AsyncMock()
        panel = make_panel(transcript_service=transcript_service, task_service=task_service)
        panel._ask_transcribe = AsyncMock(return_value=None)
        await panel.load()

        await panel.transcribe_source_clicked(MagicMock(control=MagicMock(data="alice.mp3")))

        transcript_service.assign_speaker.assert_not_awaited()
        task_service.queue_transcribe.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_missing_file_is_refused_before_the_dialog_opens(self, make_panel):
        transcript_service = AsyncMock()
        transcript_service.list_audio_sources.return_value = [source(missing=True)]
        task_service = AsyncMock()
        panel = make_panel(transcript_service=transcript_service, task_service=task_service)
        panel._ask_transcribe = AsyncMock()
        await panel.load()

        await panel.transcribe_source_clicked(MagicMock(control=MagicMock(data="alice.mp3")))

        panel._ask_transcribe.assert_not_awaited()
        task_service.queue_transcribe.assert_not_awaited()
        panel.show_snackbar.assert_called_once()

    @pytest.mark.asyncio
    async def test_the_dialog_is_offered_every_workspace_wide_speaker(
        self, make_panel, attach_page
    ):
        transcript_service = AsyncMock()
        transcript_service.list_audio_sources.return_value = [source()]
        transcript_service.speaker_suggestions.return_value = ["Alice", "Zoe"]
        panel = make_panel(transcript_service=transcript_service)
        attach_page(SourcesPanel)
        await panel.load()

        task = asyncio.ensure_future(panel._ask_transcribe(panel.sources["alice.mp3"]))
        await asyncio.sleep(0)

        transcript_service.speaker_suggestions.assert_awaited_with(panel.chronicle.id)
        task.cancel()


class TestNormalizeAction:
    @pytest.mark.asyncio
    async def test_an_unnormalized_source_offers_the_action(self, panel_with):
        panel, _ = panel_with([source()])

        await panel.load()

        tooltips = [c.tooltip for c in panel.source_list.controls[0].controls[1:]]
        assert "Normalize this track" in tooltips

    @pytest.mark.asyncio
    async def test_a_normalized_source_does_not_offer_it(self, panel_with):
        panel, _ = panel_with(
            [
                source(
                    normalization_state=SourceState.DONE,
                    normalized_hash="h",
                    normalized_filename="alice.normalized.wav",
                )
            ]
        )

        await panel.load()

        tooltips = [c.tooltip for c in panel.source_list.controls[0].controls[1:]]
        assert "Normalize this track" not in tooltips

    @pytest.mark.asyncio
    async def test_a_missing_source_does_not_offer_it(self, panel_with):
        panel, _ = panel_with([source(missing=True)])

        await panel.load()

        tooltips = [c.tooltip for c in panel.source_list.controls[0].controls[1:]]
        assert "Normalize this track" not in tooltips

    @pytest.mark.asyncio
    async def test_clicking_queues_a_normalize_task(self, make_panel):
        transcript_service = AsyncMock()
        transcript_service.list_audio_sources.return_value = [source()]
        task_service = AsyncMock()
        panel = make_panel(transcript_service=transcript_service, task_service=task_service)
        await panel.load()

        await panel.normalize_source_clicked(MagicMock(control=MagicMock(data="alice.mp3")))

        task_service.queue_normalize.assert_awaited_once_with(panel.chronicle.id, "/s/alice.mp3")
        panel.show_snackbar.assert_called_once()

    @pytest.mark.asyncio
    async def test_a_normalized_source_says_so_in_its_status(self, panel_with):
        panel, _ = panel_with(
            [
                source(
                    normalization_state=SourceState.DONE,
                    normalized_hash="h",
                    normalized_filename="alice.normalized.wav",
                )
            ]
        )

        await panel.load()

        assert "Normalized" in panel.source_list.controls[0].controls[0].controls[1].value
