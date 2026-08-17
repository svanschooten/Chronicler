"""Tests for the Sources panel - listing a chronicle's audio tracks and queueing one
for transcription."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from chronicler.core.models import Chronicle
from chronicler.desktop.theme import theme_colors
from chronicler.desktop.views.transcript.sources import SourcesPanel


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
        # Not attached to a live page, so the control can't push an update.
        panel.source_list.update = MagicMock()
        return panel

    return _make


@pytest.mark.asyncio
async def test_load_shows_a_placeholder_when_there_are_no_sources(make_panel):
    transcript_service = AsyncMock()
    transcript_service.list_audio_sources.return_value = []
    panel = make_panel(transcript_service=transcript_service)

    await panel.load()

    assert len(panel.source_list.controls) == 1
    assert "No audio sources" in panel.source_list.controls[0].value


@pytest.mark.asyncio
async def test_load_lists_one_row_per_source_labelled_by_filename(make_panel):
    transcript_service = AsyncMock()
    transcript_service.list_audio_sources.return_value = [
        "/workspace/chronicles/x/sources/alice.mp3",
        "/workspace/chronicles/x/sources/bob.mp3",
    ]
    panel = make_panel(transcript_service=transcript_service)

    await panel.load()

    assert len(panel.source_list.controls) == 2
    labels = [row.controls[0].value for row in panel.source_list.controls]
    assert labels == ["alice.mp3", "bob.mp3"]
    # The full path travels on the button's data - the label is only for reading.
    assert panel.source_list.controls[0].controls[1].data.endswith("alice.mp3")


@pytest.mark.asyncio
async def test_load_degrades_to_the_empty_state_when_listing_fails(make_panel):
    transcript_service = AsyncMock()
    transcript_service.list_audio_sources.side_effect = RuntimeError("no such directory")
    panel = make_panel(transcript_service=transcript_service)

    await panel.load()

    assert "No audio sources" in panel.source_list.controls[0].value


@pytest.mark.asyncio
async def test_refresh_clicked_reloads(make_panel):
    transcript_service = AsyncMock()
    transcript_service.list_audio_sources.return_value = []
    panel = make_panel(transcript_service=transcript_service)

    await panel.refresh_clicked(MagicMock())

    transcript_service.list_audio_sources.assert_awaited_once()


@pytest.mark.asyncio
async def test_transcribe_source_queues_a_task_for_the_chosen_speaker(make_panel):
    task_service = AsyncMock()
    panel = make_panel(task_service=task_service)
    panel._ask_speaker_name = AsyncMock(return_value="Alice")

    await panel.transcribe_source_clicked(MagicMock(control=MagicMock(data="/s/alice.mp3")))

    task_service.queue_transcribe.assert_awaited_once_with(
        panel.chronicle.id, "/s/alice.mp3", "Alice"
    )
    panel.show_snackbar.assert_called_once()


@pytest.mark.asyncio
async def test_transcribe_source_does_nothing_when_the_speaker_prompt_is_cancelled(make_panel):
    task_service = AsyncMock()
    panel = make_panel(task_service=task_service)
    panel._ask_speaker_name = AsyncMock(return_value=None)

    await panel.transcribe_source_clicked(MagicMock(control=MagicMock(data="/s/alice.mp3")))

    task_service.queue_transcribe.assert_not_awaited()


@pytest.mark.asyncio
async def test_ask_speaker_name_offers_existing_names_as_a_hint(make_panel, attach_page):
    """Existing names are a hint, not a locked-in choice: get_or_create_speaker matches
    by exact name, so typing one exactly reuses that speaker rather than creating a
    near-duplicate."""
    transcript_service = AsyncMock()
    transcript_service.list_speaker_names.return_value = ["Alice", "Bob"]
    panel = make_panel(transcript_service=transcript_service)
    page = attach_page(SourcesPanel)

    task = asyncio.ensure_future(panel._ask_speaker_name("alice.mp3"))
    await asyncio.sleep(0)

    (dialog,), _ = page.show_dialog.call_args
    speaker_field = dialog.content.controls[1]
    assert speaker_field.hint_text == "Alice, Bob"
    assert "alice.mp3" in dialog.title.value

    speaker_field.value = "Carol"
    await dialog.actions[1].on_click(MagicMock())

    assert await asyncio.wait_for(task, timeout=1) == "Carol"


@pytest.mark.asyncio
async def test_ask_speaker_name_hints_an_example_when_there_are_no_speakers_yet(
    make_panel, attach_page
):
    transcript_service = AsyncMock()
    transcript_service.list_speaker_names.return_value = []
    panel = make_panel(transcript_service=transcript_service)
    page = attach_page(SourcesPanel)

    task = asyncio.ensure_future(panel._ask_speaker_name("alice.mp3"))
    await asyncio.sleep(0)

    (dialog,), _ = page.show_dialog.call_args
    assert dialog.content.controls[1].hint_text == "e.g. Alice"

    await dialog.actions[0].on_click(MagicMock())
    assert await asyncio.wait_for(task, timeout=1) is None
