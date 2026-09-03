"""Tests for the Sources panel - a chronicle's audio tracks and the actions on them."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from chronicler.core.models import AudioSource, Chronicle, SourceState
from chronicler.desktop.theme import theme_colors
from chronicler.desktop.views.transcript.sources import SourcesPanel


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


class TestTranscribing:
    @pytest.mark.asyncio
    async def test_uses_the_remembered_speaker_without_prompting(self, make_panel):
        transcript_service = AsyncMock()
        transcript_service.list_audio_sources.return_value = [source(speaker_name="Alice")]
        task_service = AsyncMock()
        panel = make_panel(transcript_service=transcript_service, task_service=task_service)
        panel._ask_speaker = AsyncMock()
        await panel.load()

        await panel.transcribe_source_clicked(MagicMock(control=MagicMock(data="alice.mp3")))

        panel._ask_speaker.assert_not_awaited()
        task_service.queue_transcribe.assert_awaited_once()
        assert task_service.queue_transcribe.await_args.args[2] == "Alice"

    @pytest.mark.asyncio
    async def test_prompts_when_the_source_has_no_speaker_yet(self, make_panel):
        transcript_service = AsyncMock()
        transcript_service.list_audio_sources.return_value = [source()]
        task_service = AsyncMock()
        panel = make_panel(transcript_service=transcript_service, task_service=task_service)
        panel._ask_speaker = AsyncMock(return_value="Carol")
        await panel.load()

        await panel.transcribe_source_clicked(MagicMock(control=MagicMock(data="alice.mp3")))

        panel._ask_speaker.assert_awaited_once()
        transcript_service.assign_speaker.assert_awaited_once_with(
            panel.chronicle.id, "alice.mp3", "Carol"
        )
        assert task_service.queue_transcribe.await_args.args[2] == "Carol"

    @pytest.mark.asyncio
    async def test_a_cancelled_prompt_queues_nothing(self, make_panel):
        transcript_service = AsyncMock()
        transcript_service.list_audio_sources.return_value = [source()]
        task_service = AsyncMock()
        panel = make_panel(transcript_service=transcript_service, task_service=task_service)
        panel._ask_speaker = AsyncMock(return_value=None)
        await panel.load()

        await panel.transcribe_source_clicked(MagicMock(control=MagicMock(data="alice.mp3")))

        task_service.queue_transcribe.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_missing_file_is_refused(self, make_panel):
        transcript_service = AsyncMock()
        transcript_service.list_audio_sources.return_value = [source(missing=True)]
        task_service = AsyncMock()
        panel = make_panel(transcript_service=transcript_service, task_service=task_service)
        await panel.load()

        await panel.transcribe_source_clicked(MagicMock(control=MagicMock(data="alice.mp3")))

        task_service.queue_transcribe.assert_not_awaited()
        panel.show_snackbar.assert_called_once()


class TestSpeakerAssignment:
    @pytest.mark.asyncio
    async def test_assign_speaker_persists_and_reloads(self, make_panel):
        transcript_service = AsyncMock()
        transcript_service.list_audio_sources.return_value = [source()]
        panel = make_panel(transcript_service=transcript_service)
        panel._ask_speaker = AsyncMock(return_value="Dave")
        await panel.load()

        await panel.assign_speaker_clicked(MagicMock(control=MagicMock(data="alice.mp3")))

        transcript_service.assign_speaker.assert_awaited_once_with(
            panel.chronicle.id, "alice.mp3", "Dave"
        )

    @pytest.mark.asyncio
    async def test_cancelling_assignment_changes_nothing(self, make_panel):
        transcript_service = AsyncMock()
        transcript_service.list_audio_sources.return_value = [source()]
        panel = make_panel(transcript_service=transcript_service)
        panel._ask_speaker = AsyncMock(return_value=None)
        await panel.load()

        await panel.assign_speaker_clicked(MagicMock(control=MagicMock(data="alice.mp3")))

        transcript_service.assign_speaker.assert_not_awaited()


class TestSpeakerPrompt:
    @pytest.mark.asyncio
    async def test_offers_known_speakers_as_selectable_options(self, panel_with, attach_page):
        panel, _ = panel_with([], speakers=["Alice", "Bob"])
        page = attach_page(SourcesPanel)

        task = asyncio.ensure_future(panel._ask_speaker("alice.mp3", None))
        await asyncio.sleep(0)

        (dialog,), _ = page.show_dialog.call_args
        dropdown = dialog.content.controls[1]
        assert [option.key for option in dropdown.options] == ["Alice", "Bob"]
        assert "alice.mp3" in dialog.title.value

        dropdown.value = "Bob"
        await dialog.actions[1].on_click(MagicMock())

        assert await asyncio.wait_for(task, timeout=1) == "Bob"

    @pytest.mark.asyncio
    async def test_preselects_the_current_speaker(self, panel_with, attach_page):
        panel, _ = panel_with([], speakers=["Alice", "Bob"])
        page = attach_page(SourcesPanel)

        task = asyncio.ensure_future(panel._ask_speaker("alice.mp3", "Bob"))
        await asyncio.sleep(0)

        (dialog,), _ = page.show_dialog.call_args
        assert dialog.content.controls[1].value == "Bob"

        await dialog.actions[0].on_click(MagicMock())
        await asyncio.wait_for(task, timeout=1)

    @pytest.mark.asyncio
    async def test_a_typed_new_name_wins_over_the_dropdown(self, panel_with, attach_page):
        panel, _ = panel_with([], speakers=["Alice"])
        page = attach_page(SourcesPanel)

        task = asyncio.ensure_future(panel._ask_speaker("alice.mp3", None))
        await asyncio.sleep(0)

        (dialog,), _ = page.show_dialog.call_args
        dialog.content.controls[1].value = "Alice"
        dialog.content.controls[2].value = "Carol"
        await dialog.actions[1].on_click(MagicMock())

        assert await asyncio.wait_for(task, timeout=1) == "Carol"

    @pytest.mark.asyncio
    async def test_cancelling_resolves_to_none(self, panel_with, attach_page):
        panel, _ = panel_with([], speakers=[])
        page = attach_page(SourcesPanel)

        task = asyncio.ensure_future(panel._ask_speaker("alice.mp3", None))
        await asyncio.sleep(0)

        (dialog,), _ = page.show_dialog.call_args
        await dialog.actions[0].on_click(MagicMock())

        assert await asyncio.wait_for(task, timeout=1) is None


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
