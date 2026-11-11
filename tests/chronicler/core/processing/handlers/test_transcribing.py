"""Tests for the TRANSCRIBE task handler."""

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import text

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import Chronicle, Task, TaskType, TranscriptLine
from chronicler.core.processing.handlers import WorkerHandlers
from chronicler.core.sqlite import (
    SQLiteAudioSourceRepository,
    SQLiteChronicleRepository,
    SQLiteTranscriptRepository,
)
from tests.chronicler.core.processing.handlers.helpers import read_chronicle
from tests.projects import register_chronicle


@pytest.fixture(autouse=True)
def _defaults_not_the_developers_config(isolated_config):
    """
    `Settings()` here has to mean the shipped defaults.

    Without this it reads whatever is in ~/.config/Chronicler, so a machine with a real
    language model configured ran these against it - one of them over the network. See
    docs/testing.md.
    """


async def _noop_progress(_progress: int) -> None:
    pass


def _fake_transcription(*segments):
    """
    Stands in for transcribe_audio, which labels every segment with the speaker whose track
    it was handed - so does this, or the stub wouldn't honour the real contract and the
    handler's plumbing would be tested against a fiction.
    """

    def _transcribe(_path: str, speaker_name: str, **_kwargs) -> list[TranscriptLine]:
        return [
            TranscriptLine(speaker_name=speaker_name, text=text, start_time=start, end_time=end)
            for text, start, end in segments
        ]

    return _transcribe


async def _make_transcribe_task(
    db_manager, chronicle_id, speaker_name, filename="recording.mp3", **extra
):
    """
    The file must already live in the chronicle's durable sources/ directory - that's
    ChronicleService.add_audio_source's job, a separate earlier step from transcribing it
    (see TODO.md).
    """
    await register_chronicle(db_manager, chronicle_id)
    sources_dir = db_manager.get_chronicle_sources_path(str(chronicle_id))
    audio_file = sources_dir / filename
    audio_file.write_bytes(b"fake audio bytes")
    return (
        Task(
            type=TaskType.TRANSCRIBE,
            chronicle_id=chronicle_id,
            data=json.dumps({"file_path": str(audio_file), "speaker_name": speaker_name, **extra}),
        ),
        audio_file,
    )


@pytest.mark.asyncio
async def test_handle_transcribe_creates_lines_for_assigned_speaker(tmp_path):
    """
    transcribe_audio itself is mocked - it's a real, potentially multi-hundred-MB model
    download plus real CPU transcription, not something a unit test should trigger.
    """
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            chronicle = await chronicle_repo.create(Chronicle(title="Recording"))

            handlers = WorkerHandlers(db_manager, archive_sessions=db_manager.get_archive_session)
            task, audio_file = await _make_transcribe_task(db_manager, chronicle.id, "Alice")

            with patch(
                "chronicler.core.processing.transcriber.transcribe_audio",
                side_effect=_fake_transcription(
                    ("Hello there", 0.0, 1.0), ("General Kenobi", 1.0, 2.0)
                ),
            ):
                await handlers.handle_transcribe(task, _noop_progress)

            assert audio_file.exists()

            session = await db_manager.get_project_session(str(chronicle.id))
            async with session:
                repo = SQLiteTranscriptRepository(session)
                lines = await repo.get_lines()
            assert [line.text for line in lines] == ["Hello there", "General Kenobi"]
            assert all(line.speaker_name == "Alice" for line in lines)

            updated = await read_chronicle(db_manager, chronicle.id)
            assert updated.speakers_count == 1
            assert [t.name for t in updated.tags] == ["Transcript"]
            assert updated.duration == "2s"
            assert updated.status == "Transcribed"
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_handle_transcribe_duration_reflects_longest_track(tmp_path):
    """
    Duration is the max end_time across every speaker's track, not just the one just
    transcribed - two participants' tracks from the same session can run to different
    lengths, and the chronicle's duration is the longer of the two.
    """
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            chronicle = await chronicle_repo.create(Chronicle(title="Podcast"))

            handlers = WorkerHandlers(db_manager, archive_sessions=db_manager.get_archive_session)

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

            updated = await read_chronicle(db_manager, chronicle.id)
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

            handlers = WorkerHandlers(db_manager, archive_sessions=db_manager.get_archive_session)
            task, _ = await _make_transcribe_task(db_manager, chronicle.id, "Alice")
            with patch(
                "chronicler.core.processing.transcriber.transcribe_audio",
                side_effect=_fake_transcription(("Hi", 0.0, 1.0)),
            ):
                await handlers.handle_transcribe(task, _noop_progress)

            updated = await read_chronicle(db_manager, chronicle.id)
            assert updated.status == "Archived"
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_handle_transcribe_keeps_other_speakers_lines(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            chronicle = await chronicle_repo.create(Chronicle(title="Podcast"))
            handlers = WorkerHandlers(db_manager, archive_sessions=db_manager.get_archive_session)

            await _transcribe(handlers, db_manager, chronicle.id, "Alice", "alice.mp3", "Hi")
            await _transcribe(handlers, db_manager, chronicle.id, "Bob", "bob.mp3", "Hello")
            await _transcribe(handlers, db_manager, chronicle.id, "Alice", "alice.mp3", "Hey")

            assert await _texts(db_manager, chronicle.id) == {("Alice", "Hey"), ("Bob", "Hello")}

            updated = await read_chronicle(db_manager, chronicle.id)
            assert updated.speakers_count == 2
    finally:
        await db_manager.close_all()


async def _transcribe(handlers, db_manager, chronicle_id, speaker, filename, *texts, **extra):
    """Runs one transcribe task whose stubbed output is `texts`, one second each."""
    task, _ = await _make_transcribe_task(db_manager, chronicle_id, speaker, filename, **extra)
    segments = [(text, float(index), float(index + 1)) for index, text in enumerate(texts)]
    with patch(
        "chronicler.core.processing.transcriber.transcribe_audio",
        side_effect=_fake_transcription(*segments),
    ):
        await handlers.handle_transcribe(task, _noop_progress)


async def _lines(db_manager, chronicle_id):
    await register_chronicle(db_manager, chronicle_id)
    session = await db_manager.get_project_session(str(chronicle_id))
    async with session:
        return await SQLiteTranscriptRepository(session).get_lines()


async def _texts(db_manager, chronicle_id):
    return {(line.speaker_name, line.text) for line in await _lines(db_manager, chronicle_id)}


class TestTwoTracksForOneSpeaker:
    @pytest.mark.asyncio
    async def test_both_tracks_are_kept(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        handlers = WorkerHandlers(db_manager)
        chronicle_id = uuid4()
        try:
            await _transcribe(handlers, db_manager, chronicle_id, "Alice", "part1.wav", "One")
            await _transcribe(handlers, db_manager, chronicle_id, "Alice", "part2.wav", "Two")

            assert await _texts(db_manager, chronicle_id) == {("Alice", "One"), ("Alice", "Two")}
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_rerunning_one_track_replaces_only_its_lines(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        handlers = WorkerHandlers(db_manager)
        chronicle_id = uuid4()
        try:
            await _transcribe(handlers, db_manager, chronicle_id, "Alice", "part1.wav", "One")
            await _transcribe(handlers, db_manager, chronicle_id, "Alice", "part2.wav", "Two")
            await _transcribe(handlers, db_manager, chronicle_id, "Alice", "part2.wav", "Again")

            assert await _texts(db_manager, chronicle_id) == {
                ("Alice", "One"),
                ("Alice", "Again"),
            }
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_each_line_records_its_track(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        handlers = WorkerHandlers(db_manager)
        chronicle_id = uuid4()
        try:
            await _transcribe(handlers, db_manager, chronicle_id, "Alice", "part1.wav", "One")
            await _transcribe(handlers, db_manager, chronicle_id, "Alice", "part2.wav", "Two")

            session = await db_manager.get_project_session(str(chronicle_id))
            async with session:
                sources = {
                    source.id: source.filename
                    for source in await SQLiteAudioSourceRepository(session).list_sources()
                }
            lines = await _lines(db_manager, chronicle_id)
            assert {(line.text, sources[line.source_id]) for line in lines} == {
                ("One", "part1.wav"),
                ("Two", "part2.wav"),
            }
        finally:
            await db_manager.close_all()


async def _forget_line_sources(db_manager, chronicle_id) -> None:
    """Makes every line look like one written before lines recorded their track."""
    session = await db_manager.get_project_session(str(chronicle_id))
    async with session:
        await session.execute(text("UPDATE transcript_lines SET source_id = NULL"))
        await session.commit()


async def _import_line(db_manager, chronicle_id, speaker, text) -> None:
    """A line the way an import writes it: a speaker, but no track."""
    await register_chronicle(db_manager, chronicle_id)
    session = await db_manager.get_project_session(str(chronicle_id))
    async with session:
        repo = SQLiteTranscriptRepository(session)
        owner = await repo.get_or_create_speaker(speaker)
        await repo.add_lines(
            [TranscriptLine(speaker_id=owner.id, text=text, start_time=0, end_time=1)]
        )
        await session.commit()


class TestLinesWithNoRecordedTrack:
    @pytest.mark.asyncio
    async def test_an_imported_line_survives_rerunning_the_speakers_only_track(self, tmp_path):
        """Review repro: the old 'only track owns untracked lines' rule deleted this."""
        db_manager = DatabaseManager(tmp_path)
        handlers = WorkerHandlers(db_manager)
        chronicle_id = uuid4()
        try:
            await _import_line(db_manager, chronicle_id, "Alice", "Imported")
            await _transcribe(handlers, db_manager, chronicle_id, "Alice", "alice.wav", "Heard")
            await _transcribe(handlers, db_manager, chronicle_id, "Alice", "alice.wav", "Again")

            assert await _texts(db_manager, chronicle_id) == {
                ("Alice", "Imported"),
                ("Alice", "Again"),
            }
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_they_are_kept_when_the_speaker_has_two_tracks(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        handlers = WorkerHandlers(db_manager)
        chronicle_id = uuid4()
        try:
            await _transcribe(handlers, db_manager, chronicle_id, "Alice", "part1.wav", "One")
            await _transcribe(handlers, db_manager, chronicle_id, "Alice", "part2.wav", "Two")
            await _forget_line_sources(db_manager, chronicle_id)

            await _transcribe(handlers, db_manager, chronicle_id, "Alice", "part2.wav", "Again")

            assert await _texts(db_manager, chronicle_id) == {
                ("Alice", "One"),
                ("Alice", "Two"),
                ("Alice", "Again"),
            }
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_an_imported_transcript_survives_a_first_transcription(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        handlers = WorkerHandlers(db_manager)
        chronicle_id = uuid4()
        try:
            await register_chronicle(db_manager, chronicle_id)
            session = await db_manager.get_project_session(str(chronicle_id))
            async with session:
                repo = SQLiteTranscriptRepository(session)
                alice = await repo.get_or_create_speaker("Alice")
                await repo.add_lines(
                    [TranscriptLine(speaker_id=alice.id, text="Imported", start_time=0, end_time=1)]
                )
                await session.commit()

            await _transcribe(handlers, db_manager, chronicle_id, "Alice", "alice.wav", "Heard")

            assert await _texts(db_manager, chronicle_id) == {
                ("Alice", "Imported"),
                ("Alice", "Heard"),
            }
        finally:
            await db_manager.close_all()


class TestStartOffset:
    @pytest.mark.asyncio
    async def test_it_shifts_the_tracks_timestamps(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        handlers = WorkerHandlers(db_manager)
        chronicle_id = uuid4()
        try:
            await _transcribe(
                handlers, db_manager, chronicle_id, "Alice", "part2.wav", "Two", start_offset=60
            )

            (line,) = await _lines(db_manager, chronicle_id)
            assert (line.start_time, line.end_time) == (60.0, 61.0)
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_a_rerun_keeps_the_stored_offset(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        handlers = WorkerHandlers(db_manager)
        chronicle_id = uuid4()
        try:
            await _transcribe(
                handlers, db_manager, chronicle_id, "Alice", "part2.wav", "Two", start_offset=60
            )
            await _transcribe(handlers, db_manager, chronicle_id, "Alice", "part2.wav", "Again")

            (line,) = await _lines(db_manager, chronicle_id)
            assert (line.text, line.start_time) == ("Again", 60.0)
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

        with patch(
            "chronicler.core.processing.transcriber.transcribe_audio",
            side_effect=ImportError("No module named 'faster_whisper'"),
        ):
            with pytest.raises(RuntimeError, match="transcription"):
                await handlers.handle_transcribe(task, _noop_progress)
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_handle_transcribe_passes_the_assigned_speaker_to_the_transcriber(tmp_path):
    """
    The speaker whose track this is, is known before a single segment exists - so it's an
    input to transcription, not a label the handler stamps over a placeholder afterwards.
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

        transcribe.assert_called_once()
        assert transcribe.call_args.args == (str(audio_file), "Alice")
    finally:
        await db_manager.close_all()


class TestTranscriptionParameters:
    async def _run(self, tmp_path, settings=None, task_overrides=None):
        db_manager = DatabaseManager(tmp_path)
        await db_manager.init_archive()
        handlers = WorkerHandlers(db_manager, settings=settings)
        chronicle_id = uuid4()
        task, audio_file = await _make_transcribe_task(db_manager, chronicle_id, "GM")
        if task_overrides:
            data = json.loads(task.data)
            data.update(task_overrides)
            task.data = json.dumps(data)

        captured = {}

        def fake(_path, speaker_name, **kwargs):
            captured.update(kwargs)
            return []

        with patch("chronicler.core.processing.transcriber.transcribe_audio", side_effect=fake):
            await handlers.handle_transcribe(task, _noop_progress)
        return db_manager, chronicle_id, captured, audio_file

    @pytest.mark.asyncio
    async def test_settings_defaults_reach_the_transcriber(self, tmp_path):
        from chronicler.core.config import Settings

        settings = Settings()
        settings.transcription.language = "nl"
        settings.transcription.no_speech_threshold = 0.35
        settings.transcription.model_size = "small"

        db_manager, _, captured, _ = await self._run(tmp_path, settings)
        try:
            assert captured["language"] == "nl"
            assert captured["no_speech_threshold"] == 0.35
            assert captured["model_size"] == "small"
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_task_parameters_override_the_settings(self, tmp_path):
        from chronicler.core.config import Settings

        settings = Settings()
        settings.transcription.language = "nl"

        db_manager, _, captured, _ = await self._run(
            tmp_path, settings, {"language": "de", "no_speech_threshold": 0.9}
        )
        try:
            assert captured["language"] == "de"
            assert captured["no_speech_threshold"] == 0.9
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_auto_on_the_task_beats_a_configured_language(self, tmp_path):
        from chronicler.core.config import Settings

        settings = Settings()
        settings.transcription.language = "nl"

        db_manager, _, captured, _ = await self._run(tmp_path, settings, {"language": "auto"})
        try:
            assert captured["language"] is None
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_the_source_record_remembers_what_was_used(self, tmp_path):
        from chronicler.core.config import Settings
        from chronicler.core.sqlite import SQLiteAudioSourceRepository

        settings = Settings()
        settings.transcription.language = "nl"
        settings.transcription.model_size = "small"

        db_manager, chronicle_id, _, _ = await self._run(tmp_path, settings)
        try:
            session = await db_manager.get_project_session(str(chronicle_id))
            async with session:
                record = await SQLiteAudioSourceRepository(session).get_by_filename("recording.mp3")

            assert record is not None
            assert record.transcription_state.value == "DONE"
            assert record.transcription_language == "nl"
            assert record.transcription_model == "small"
            assert record.is_transcribed is True
            assert record.speaker_name == "GM"
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_a_failure_is_recorded_on_the_source_record(self, tmp_path):
        from chronicler.core.sqlite import SQLiteAudioSourceRepository

        db_manager = DatabaseManager(tmp_path)
        await db_manager.init_archive()
        try:
            handlers = WorkerHandlers(db_manager)
            chronicle_id = uuid4()
            task, _ = await _make_transcribe_task(db_manager, chronicle_id, "GM")

            with patch(
                "chronicler.core.processing.transcriber.transcribe_audio",
                side_effect=RuntimeError("model exploded"),
            ):
                with pytest.raises(RuntimeError):
                    await handlers.handle_transcribe(task, _noop_progress)

            session = await db_manager.get_project_session(str(chronicle_id))
            async with session:
                record = await SQLiteAudioSourceRepository(session).get_by_filename("recording.mp3")

            assert record.transcription_state.value == "FAILED"
            assert "model exploded" in record.transcription_error
        finally:
            await db_manager.close_all()


@pytest.mark.asyncio
async def test_progress_moves_through_the_transcription(tmp_path):
    """The transcriber reports from its own thread; each step reaches update_progress."""
    db_manager = DatabaseManager(tmp_path)
    handlers = WorkerHandlers(db_manager)
    chronicle_id = uuid4()
    reported: list[int] = []

    async def record(progress: int) -> None:
        reported.append(progress)

    def transcribe(_path, speaker_name, on_progress=None, **_kwargs):
        for fraction in (0.25, 0.5, 1.0):
            on_progress(fraction)
        return [TranscriptLine(speaker_name=speaker_name, text="Hi", start_time=0, end_time=1)]

    try:
        task, _ = await _make_transcribe_task(db_manager, chronicle_id, "Alice")
        with patch(
            "chronicler.core.processing.transcriber.transcribe_audio", side_effect=transcribe
        ):
            await handlers.handle_transcribe(task, record)

        assert reported == [10, 30, 40, 50, 70, 70, 100]
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_a_cancelled_transcription_marks_the_source_and_writes_no_lines(tmp_path):
    from chronicler.core.cancellation import TaskCancelledError

    db_manager = DatabaseManager(tmp_path)
    handlers = WorkerHandlers(db_manager)
    chronicle_id = uuid4()

    def transcribe(*_args, **_kwargs):
        raise TaskCancelledError("The task was cancelled")

    try:
        task, _ = await _make_transcribe_task(db_manager, chronicle_id, "Alice")
        with (
            patch(
                "chronicler.core.processing.transcriber.transcribe_audio", side_effect=transcribe
            ),
            pytest.raises(TaskCancelledError),
        ):
            await handlers.handle_transcribe(task, _noop_progress)

        assert await _lines(db_manager, chronicle_id) == []
    finally:
        await db_manager.close_all()
