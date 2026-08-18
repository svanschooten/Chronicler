"""Tests for ImportCoordinator.

No Flet involved: this is the part of an import that decides what happens to the
workspace, which is exactly the part worth testing without a page attached.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from chronicler.core.file_staging import stage_local_file
from chronicler.core.models import Chronicle
from chronicler.desktop.views.archive.imports import ImportCoordinator, TranscriptImportOptions


@pytest.fixture
def imports_dir(tmp_path):
    directory = tmp_path / "workspace" / "imports"
    directory.mkdir(parents=True)
    return directory


@pytest.fixture
def make_coordinator(imports_dir):
    def _make(chronicle_service=None, task_service=None, transcript_service=None):
        async def stage_file(local_path: str) -> str:
            return str(stage_local_file(Path(local_path), imports_dir))

        return ImportCoordinator(
            chronicle_service or AsyncMock(),
            task_service or AsyncMock(),
            transcript_service or AsyncMock(),
            stage_file,
        )

    return _make


@pytest.fixture
def picked_file(tmp_path):
    def _make(name: str, content: str = "content") -> Path:
        path = tmp_path / "Downloads" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    return _make


async def _never_asked() -> str:
    raise AssertionError("the overwrite/append prompt should not have been reached")


# -- audio ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_audio_stages_a_file_from_outside_the_workspace(
    make_coordinator, imports_dir, picked_file
):
    """Importing an audio source doesn't queue a transcription - it stages the file and
    hands it to add_audio_source. Transcribing a specific source with a speaker
    assigned is a separate action, from the transcript view's Sources panel."""
    chronicle_service = AsyncMock()
    coordinator = make_coordinator(chronicle_service=chronicle_service)
    chronicle_id = uuid4()

    await coordinator.import_audio(chronicle_id, str(picked_file("recording.mp3")))

    called_id, staged_path, original_name = chronicle_service.add_audio_source.call_args.args
    assert called_id == chronicle_id
    assert Path(staged_path).resolve().is_relative_to(imports_dir.resolve())
    # Staging deliberately renames to a throwaway UUID; the original name travels
    # separately so the durable copy can still be readable.
    assert Path(staged_path).name != "recording.mp3"
    assert original_name == "recording.mp3"


@pytest.mark.asyncio
async def test_import_audio_without_a_chronicle_creates_one_named_after_the_file(
    make_coordinator, picked_file
):
    """create_chronicle gets no source_file= - the file lives in the durable sources/
    dir now, and a single source_file field can't represent a chronicle with multiple
    tracks anyway."""
    chronicle_service = AsyncMock()
    chronicle_service.create_chronicle.return_value = Chronicle(title="recording")
    coordinator = make_coordinator(chronicle_service=chronicle_service)

    message = await coordinator.import_audio(None, str(picked_file("recording.mp3")))

    chronicle_service.create_chronicle.assert_awaited_once_with("recording")
    chronicle_service.add_audio_source.assert_awaited_once()
    assert "recording" in message


# -- transcript ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_transcript_without_a_chronicle_creates_one_and_queues(
    make_coordinator, imports_dir, picked_file
):
    chronicle_service = AsyncMock()
    chronicle_service.create_chronicle.return_value = Chronicle(title="transcript")
    task_service = AsyncMock()
    coordinator = make_coordinator(chronicle_service=chronicle_service, task_service=task_service)

    await coordinator.import_transcript(
        None,
        str(picked_file("transcript.txt", "Alice: hi\n")),
        TranscriptImportOptions(),
        _never_asked,
    )

    chronicle_service.create_chronicle.assert_awaited_once()
    _chronicle_id, queued_path = task_service.queue_import.call_args.args
    assert Path(queued_path).resolve().is_relative_to(imports_dir.resolve())
    assert task_service.queue_import.call_args.kwargs["timestamp_group"] is None
    assert task_service.queue_import.call_args.kwargs["append"] is False


@pytest.mark.asyncio
async def test_import_transcript_passes_through_the_parse_options(make_coordinator, picked_file):
    task_service = AsyncMock()
    transcript_service = AsyncMock()
    transcript_service.get_transcript.return_value = []
    coordinator = make_coordinator(task_service=task_service, transcript_service=transcript_service)
    options = TranscriptImportOptions(
        regex=r"^\[(\d\d:\d\d:\d\d)\] ([A-Za-z]+):\s*(.*)$",
        speaker_group=2,
        text_group=3,
        timestamp_group=1,
    )

    await coordinator.import_transcript(
        uuid4(),
        str(picked_file("transcript.txt", "[00:00:05] Alice: hi\n")),
        options,
        _never_asked,
    )

    kwargs = task_service.queue_import.call_args.kwargs
    assert kwargs["regex"] == options.regex
    assert kwargs["speaker_group"] == 2
    assert kwargs["text_group"] == 3
    assert kwargs["timestamp_group"] == 1


@pytest.mark.asyncio
async def test_import_transcript_into_an_empty_chronicle_skips_the_prompt(
    make_coordinator, picked_file
):
    task_service = AsyncMock()
    transcript_service = AsyncMock()
    transcript_service.get_transcript.return_value = []
    coordinator = make_coordinator(task_service=task_service, transcript_service=transcript_service)

    await coordinator.import_transcript(
        uuid4(), str(picked_file("t.txt")), TranscriptImportOptions(), _never_asked
    )

    assert task_service.queue_import.call_args.kwargs["append"] is False


@pytest.mark.parametrize(
    ("choice", "expect_queued", "expect_append"),
    [("cancel", False, None), ("append", True, True), ("overwrite", True, False)],
)
@pytest.mark.asyncio
async def test_import_transcript_over_an_existing_transcript_honours_the_choice(
    make_coordinator, picked_file, choice, expect_queued, expect_append
):
    """A second transcript import would silently destroy the first, so it has to ask
    first - and then actually do what the answer said."""
    task_service = AsyncMock()
    transcript_service = AsyncMock()
    transcript_service.get_transcript.return_value = [MagicMock()]
    coordinator = make_coordinator(task_service=task_service, transcript_service=transcript_service)
    ask = AsyncMock(return_value=choice)

    message = await coordinator.import_transcript(
        uuid4(), str(picked_file("t.txt")), TranscriptImportOptions(), ask
    )

    ask.assert_awaited_once()
    if not expect_queued:
        task_service.queue_import.assert_not_awaited()
        assert message is None
    else:
        task_service.queue_import.assert_awaited_once()
        assert task_service.queue_import.call_args.kwargs["append"] is expect_append
        assert message is not None


# -- linking -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_link_chronicle_does_not_stage_the_external_file(
    make_coordinator, imports_dir, tmp_path
):
    """A linked chronicle references an external project.db directly - copying it into
    the workspace would defeat the point of linking."""
    external_db = tmp_path / "external" / "project.db"
    external_db.parent.mkdir(parents=True)
    external_db.write_text("not a real db")
    chronicle_service = AsyncMock()
    coordinator = make_coordinator(chronicle_service=chronicle_service)

    await coordinator.link_chronicle(str(external_db))

    kwargs = chronicle_service.create_chronicle.call_args.kwargs
    assert kwargs["project_path"] == str(external_db)
    assert list(imports_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_link_chronicle_names_it_after_the_containing_directory(make_coordinator, tmp_path):
    external_db = tmp_path / "Emberfall session 14" / "project.db"
    external_db.parent.mkdir(parents=True)
    external_db.write_text("db")
    chronicle_service = AsyncMock()
    coordinator = make_coordinator(chronicle_service=chronicle_service)

    await coordinator.link_chronicle(str(external_db))

    (title,), _ = chronicle_service.create_chronicle.call_args
    assert title == "Emberfall session 14"


@pytest.mark.asyncio
async def test_link_chronicle_falls_back_to_the_filename_inside_a_chronicles_dir(
    make_coordinator, tmp_path
):
    """ "chronicles" is the generic container directory, not a name worth showing."""
    external_db = tmp_path / "chronicles" / "session-14.db"
    external_db.parent.mkdir(parents=True)
    external_db.write_text("db")
    chronicle_service = AsyncMock()
    coordinator = make_coordinator(chronicle_service=chronicle_service)

    await coordinator.link_chronicle(str(external_db))

    (title,), _ = chronicle_service.create_chronicle.call_args
    assert title == "session-14"
