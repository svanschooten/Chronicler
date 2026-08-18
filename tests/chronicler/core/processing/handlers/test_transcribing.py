"""Tests for the TRANSCRIBE task handler.

transcribe_audio itself is always mocked here - it's a real, potentially
multi-hundred-MB model download plus real CPU transcription, not something a unit
test should trigger. What's under test is the handler's own plumbing: path
confinement, per-speaker line replacement, and chronicle metadata backfill.
"""

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import Chronicle, Task, TaskType, TranscriptLine
from chronicler.core.processing.handlers import WorkerHandlers
from chronicler.core.sqlite import SQLiteChronicleRepository, SQLiteTranscriptRepository


async def _noop_progress(_progress: int) -> None:
    pass


def _fake_transcription(*segments):
    """Stands in for transcribe_audio, which labels every segment with the speaker
    whose track it was handed - so does this, or the stub wouldn't honour the real
    contract and the handler's plumbing would be tested against a fiction."""

    def _transcribe(_path: str, speaker_name: str) -> list[TranscriptLine]:
        return [
            TranscriptLine(speaker_name=speaker_name, text=text, start_time=start, end_time=end)
            for text, start, end in segments
        ]

    return _transcribe


async def _make_transcribe_task(db_manager, chronicle_id, speaker_name, filename="recording.mp3"):
    """The file must already live in the chronicle's durable sources/ directory -
    that's ChronicleService.add_audio_source's job, a separate earlier step from
    transcribing it (see TODO.md). Tests set that up directly rather than going
    through the service, since this module is about handle_transcribe's own
    plumbing."""
    sources_dir = db_manager.get_chronicle_sources_path(str(chronicle_id))
    audio_file = sources_dir / filename
    audio_file.write_bytes(b"fake audio bytes")
    return (
        Task(
            type=TaskType.TRANSCRIBE,
            chronicle_id=chronicle_id,
            data=json.dumps({"file_path": str(audio_file), "speaker_name": speaker_name}),
        ),
        audio_file,
    )


@pytest.mark.asyncio
async def test_handle_transcribe_creates_lines_for_assigned_speaker(tmp_path):
    """transcribe_audio itself is mocked - it's a real, potentially multi-hundred-MB
    model download plus real CPU transcription, not something a unit test should
    trigger. This is testing handle_transcribe's own plumbing: speaker/tag/chronicle
    bookkeeping - not faster-whisper's accuracy.
    """
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            chronicle = await chronicle_repo.create(Chronicle(title="Recording"))

            handlers = WorkerHandlers(db_manager, chronicle_repo=chronicle_repo)
            task, audio_file = await _make_transcribe_task(db_manager, chronicle.id, "Alice")

            with patch(
                "chronicler.core.processing.transcriber.transcribe_audio",
                side_effect=_fake_transcription(
                    ("Hello there", 0.0, 1.0), ("General Kenobi", 1.0, 2.0)
                ),
            ):
                await handlers.handle_transcribe(task, _noop_progress)

            # Transcribing doesn't move/delete the source - only importing
            # (ChronicleService.add_audio_source) and re-transcribing (a different
            # speaker's line replacement) touch files/lines.
            assert audio_file.exists()

            session = await db_manager.get_project_session(str(chronicle.id))
            async with session:
                repo = SQLiteTranscriptRepository(session)
                lines = await repo.get_lines()
            assert [line.text for line in lines] == ["Hello there", "General Kenobi"]
            assert all(line.speaker_name == "Alice" for line in lines)

            updated = await chronicle_repo.get_by_id(chronicle.id)
            assert updated.speakers_count == 1
            assert [t.name for t in updated.tags] == ["Transcript"]
            assert updated.duration == "2s"
            assert updated.status == "Transcribed"
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_handle_transcribe_duration_reflects_longest_track(tmp_path):
    """Duration is the max end_time across every speaker's track, not just the one
    just transcribed - two participants' tracks from the same session can run to
    different lengths, and the chronicle's duration is the longer of the two."""
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            chronicle = await chronicle_repo.create(Chronicle(title="Podcast"))

            handlers = WorkerHandlers(db_manager, chronicle_repo=chronicle_repo)

            alice_task, _ = await _make_transcribe_task(
                db_manager, chronicle.id, "Alice", "alice.mp3"
            )
            with patch(
                "chronicler.core.processing.transcriber.transcribe_audio",
                side_effect=_fake_transcription(("Hi", 0.0, 90.0)),
            ):
                await handlers.handle_transcribe(alice_task, _noop_progress)

            bob_task, _ = await _make_transcribe_task(db_manager, chronicle.id, "Bob", "bob.mp3")
            with patch(
                "chronicler.core.processing.transcriber.transcribe_audio",
                side_effect=_fake_transcription(("Hello", 0.0, 30.0)),
            ):
                await handlers.handle_transcribe(bob_task, _noop_progress)

            updated = await chronicle_repo.get_by_id(chronicle.id)
            assert updated.duration == "1m 30s"
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_handle_transcribe_does_not_overwrite_a_non_default_status(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            chronicle = await chronicle_repo.create(Chronicle(title="Custom", status="Archived"))

            handlers = WorkerHandlers(db_manager, chronicle_repo=chronicle_repo)
            task, _ = await _make_transcribe_task(db_manager, chronicle.id, "Alice")
            with patch(
                "chronicler.core.processing.transcriber.transcribe_audio",
                side_effect=_fake_transcription(("Hi", 0.0, 1.0)),
            ):
                await handlers.handle_transcribe(task, _noop_progress)

            updated = await chronicle_repo.get_by_id(chronicle.id)
            assert updated.status == "Archived"
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_handle_transcribe_overwrites_only_the_assigned_speakers_lines(tmp_path):
    """The concrete requirement: each audio source is one speaker's track. Uploading
    a new/re-recorded track for one speaker must replace only their lines, not the
    whole chronicle's transcript - another speaker's already-transcribed track must
    survive untouched.
    """
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            chronicle = await chronicle_repo.create(Chronicle(title="Podcast"))

            handlers = WorkerHandlers(db_manager, chronicle_repo=chronicle_repo)

            alice_task, _ = await _make_transcribe_task(
                db_manager, chronicle.id, "Alice", "alice.mp3"
            )
            with patch(
                "chronicler.core.processing.transcriber.transcribe_audio",
                side_effect=_fake_transcription(("Alice line one", 0.0, 1.0)),
            ):
                await handlers.handle_transcribe(alice_task, _noop_progress)

            bob_task, _ = await _make_transcribe_task(db_manager, chronicle.id, "Bob", "bob.mp3")
            with patch(
                "chronicler.core.processing.transcriber.transcribe_audio",
                side_effect=_fake_transcription(("Bob line one", 0.5, 1.5)),
            ):
                await handlers.handle_transcribe(bob_task, _noop_progress)

            # Re-transcribe Alice's track (e.g. a corrected re-recording).
            alice_retake_task, _ = await _make_transcribe_task(
                db_manager, chronicle.id, "Alice", "alice_retake.mp3"
            )
            with patch(
                "chronicler.core.processing.transcriber.transcribe_audio",
                side_effect=_fake_transcription(("Alice corrected line", 0.0, 1.0)),
            ):
                await handlers.handle_transcribe(alice_retake_task, _noop_progress)

            session = await db_manager.get_project_session(str(chronicle.id))
            async with session:
                repo = SQLiteTranscriptRepository(session)
                lines = await repo.get_lines()

            assert {(line.speaker_name, line.text) for line in lines} == {
                ("Alice", "Alice corrected line"),
                ("Bob", "Bob line one"),
            }

            updated = await chronicle_repo.get_by_id(chronicle.id)
            assert updated.speakers_count == 2
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_handle_transcribe_requires_speaker_name(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        handlers = WorkerHandlers(db_manager)
        chronicle_id = uuid4()
        sources_dir = db_manager.get_chronicle_sources_path(str(chronicle_id))
        audio_file = sources_dir / "recording.mp3"
        audio_file.write_bytes(b"fake audio")

        task = Task(
            type=TaskType.TRANSCRIBE,
            chronicle_id=chronicle_id,
            data=json.dumps({"file_path": str(audio_file)}),
        )

        with pytest.raises(ValueError, match="speaker_name"):
            await handlers.handle_transcribe(task, _noop_progress)
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_handle_transcribe_rejects_file_path_outside_sources_dir(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        handlers = WorkerHandlers(db_manager)
        outside_file = tmp_path / "secrets.mp3"
        outside_file.write_bytes(b"not really audio")

        task = Task(
            type=TaskType.TRANSCRIBE,
            chronicle_id=uuid4(),
            data=json.dumps({"file_path": str(outside_file), "speaker_name": "Alice"}),
        )

        with pytest.raises(ValueError, match="sources directory"):
            await handlers.handle_transcribe(task, _noop_progress)
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_handle_transcribe_raises_helpful_error_without_transcription_extra(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        handlers = WorkerHandlers(db_manager)
        chronicle_id = uuid4()
        task, _ = await _make_transcribe_task(db_manager, chronicle_id, "Alice")

        with patch.dict("sys.modules", {"chronicler.core.processing.transcriber": None}):
            with pytest.raises(RuntimeError, match="transcription"):
                await handlers.handle_transcribe(task, _noop_progress)
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_handle_transcribe_passes_the_assigned_speaker_to_the_transcriber(tmp_path):
    """The speaker whose track this is, is known before a single segment exists - so
    it's an input to transcription, not a label the handler stamps over a placeholder
    afterwards.
    """
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        handlers = WorkerHandlers(db_manager)
        chronicle_id = uuid4()
        task, audio_file = await _make_transcribe_task(db_manager, chronicle_id, "Alice")

        transcribe = MagicMock(side_effect=_fake_transcription(("Hello", 0.0, 1.0)))
        with patch("chronicler.core.processing.transcriber.transcribe_audio", transcribe):
            await handlers.handle_transcribe(task, _noop_progress)

        transcribe.assert_called_once_with(str(audio_file), "Alice")
    finally:
        await db_manager.close_all()
