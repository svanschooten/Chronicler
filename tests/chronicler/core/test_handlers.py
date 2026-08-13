import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import Chronicle, Task, TaskType, TranscriptLine
from chronicler.core.processing.handlers import WorkerHandlers
from chronicler.core.sqlite import SQLiteChronicleRepository, SQLiteTranscriptRepository


async def _noop_progress(_progress: int) -> None:
    pass


@pytest.mark.asyncio
async def test_handle_import_rejects_file_path_outside_imports_dir(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        handlers = WorkerHandlers(db_manager)

        # An absolute path that is not inside <workspace>/imports at all.
        outside_file = tmp_path / "secrets.txt"
        outside_file.write_text("top secret")

        task = Task(
            type=TaskType.IMPORT,
            chronicle_id=uuid4(),
            data=json.dumps({"file_path": str(outside_file)}),
        )

        with pytest.raises(ValueError, match="imports directory"):
            await handlers.handle_import(task, _noop_progress)
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_handle_import_rejects_traversal_relative_to_imports_dir(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        handlers = WorkerHandlers(db_manager)
        imports_dir = db_manager.get_imports_path()

        # A path that starts inside imports/ but escapes via "..".
        escaping_path = imports_dir / ".." / ".." / "secrets.txt"

        task = Task(
            type=TaskType.IMPORT,
            chronicle_id=uuid4(),
            data=json.dumps({"file_path": str(escaping_path)}),
        )

        with pytest.raises(ValueError, match="imports directory"):
            await handlers.handle_import(task, _noop_progress)
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_handle_import_accepts_file_path_inside_imports_dir(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        handlers = WorkerHandlers(db_manager)
        imports_dir = db_manager.get_imports_path()

        good_file = imports_dir / "transcript.txt"
        good_file.write_text("Alice: Hello\nBob: Hi\n")

        chronicle_id = uuid4()
        task = Task(
            type=TaskType.IMPORT,
            chronicle_id=chronicle_id,
            data=json.dumps({"file_path": str(good_file)}),
        )

        await handlers.handle_import(task, _noop_progress)

        session = await db_manager.get_project_session(str(chronicle_id))
        async with session:
            repo = SQLiteTranscriptRepository(session)
            lines = await repo.get_lines()
            assert len(lines) == 2
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_handle_import_with_timestamp_group_uses_real_seconds(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        handlers = WorkerHandlers(db_manager)
        imports_dir = db_manager.get_imports_path()

        transcript_file = imports_dir / "transcript.txt"
        transcript_file.write_text("[00:00:05] Alice: Hello\n[00:01:00] Bob: Hi Alice\n")

        chronicle_id = uuid4()
        task = Task(
            type=TaskType.IMPORT,
            chronicle_id=chronicle_id,
            data=json.dumps(
                {
                    "file_path": str(transcript_file),
                    "regex": r"^\[(\d\d:\d\d:\d\d)\] ([A-Za-z]+):\s*(.*)$",
                    "speaker_group": 2,
                    "text_group": 3,
                    "timestamp_group": 1,
                }
            ),
        )

        await handlers.handle_import(task, _noop_progress)

        session = await db_manager.get_project_session(str(chronicle_id))
        async with session:
            repo = SQLiteTranscriptRepository(session)
            lines = await repo.get_lines()

        assert [line.start_time for line in lines] == [5.0, 60.0]
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_handle_clean_preserves_speaker_ids_across_runs(tmp_path):
    """Regression test: delete_all() used to wipe DBSpeaker too, so
    get_or_create_speaker() never found an existing speaker after a clean - every
    clean run assigned fresh speaker ids. delete_all_lines() must not repeat that.
    """
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        handlers = WorkerHandlers(db_manager)
        imports_dir = db_manager.get_imports_path()

        transcript_file = imports_dir / "transcript.txt"
        transcript_file.write_text("Alice:   Hello   there\nBob: Hi Alice\n")

        chronicle_id = uuid4()
        import_task = Task(
            type=TaskType.IMPORT,
            chronicle_id=chronicle_id,
            data=json.dumps({"file_path": str(transcript_file)}),
        )
        await handlers.handle_import(import_task, _noop_progress)

        session = await db_manager.get_project_session(str(chronicle_id))
        async with session:
            repo = SQLiteTranscriptRepository(session)
            speakers_before = {s.name: s.id for s in await repo.get_speakers()}

        clean_task = Task(type=TaskType.CLEAN, chronicle_id=chronicle_id)
        await handlers.handle_clean(clean_task, _noop_progress)
        await handlers.handle_clean(clean_task, _noop_progress)  # run twice for good measure

        session = await db_manager.get_project_session(str(chronicle_id))
        async with session:
            repo = SQLiteTranscriptRepository(session)
            speakers_after = {s.name: s.id for s in await repo.get_speakers()}

        assert speakers_after == speakers_before
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_handle_import_rolls_back_on_failure(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        handlers = WorkerHandlers(db_manager)
        imports_dir = db_manager.get_imports_path()

        transcript_file = imports_dir / "transcript.txt"
        transcript_file.write_text("Alice: Original line\n")

        chronicle_id = uuid4()
        task = Task(
            type=TaskType.IMPORT,
            chronicle_id=chronicle_id,
            data=json.dumps({"file_path": str(transcript_file)}),
        )
        await handlers.handle_import(task, _noop_progress)

        # A second import that fails partway through (after delete_all_lines(), before
        # commit) must not leave the transcript half-deleted.
        transcript_file.write_text("Carol: Replacement line\n")
        second_task = Task(
            type=TaskType.IMPORT,
            chronicle_id=chronicle_id,
            data=json.dumps({"file_path": str(transcript_file)}),
        )

        with patch.object(
            SQLiteTranscriptRepository, "add_lines", AsyncMock(side_effect=Exception("boom"))
        ):
            with pytest.raises(Exception, match="boom"):
                await handlers.handle_import(second_task, _noop_progress)

        session = await db_manager.get_project_session(str(chronicle_id))
        async with session:
            repo = SQLiteTranscriptRepository(session)
            lines = await repo.get_lines()
            assert len(lines) == 1
            assert lines[0].text == "Original line"
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_handle_import_tags_chronicle_and_backfills_speaker_count(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            chronicle = await chronicle_repo.create(Chronicle(title="Test Chronicle"))
            assert chronicle.speakers_count == 0

            handlers = WorkerHandlers(db_manager, chronicle_repo=chronicle_repo)
            imports_dir = db_manager.get_imports_path()
            transcript_file = imports_dir / "transcript.txt"
            transcript_file.write_text("Alice: Hello\nBob: Hi\nAlice: How are you?\n")

            task = Task(
                type=TaskType.IMPORT,
                chronicle_id=chronicle.id,
                data=json.dumps({"file_path": str(transcript_file)}),
            )
            await handlers.handle_import(task, _noop_progress)

            updated = await chronicle_repo.get_by_id(chronicle.id)
            assert updated.speakers_count == 2
            assert [t.name for t in updated.tags] == ["Transcript"]
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_handle_import_append_mode_keeps_existing_lines_and_orders_after(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        handlers = WorkerHandlers(db_manager)
        imports_dir = db_manager.get_imports_path()
        chronicle_id = uuid4()

        first_file = imports_dir / "part1.txt"
        first_file.write_text("Alice: Hello\nBob: Hi\n")
        first_task = Task(
            type=TaskType.IMPORT,
            chronicle_id=chronicle_id,
            data=json.dumps({"file_path": str(first_file)}),
        )
        await handlers.handle_import(first_task, _noop_progress)

        second_file = imports_dir / "part2.txt"
        second_file.write_text("Carol: Later on\n")
        second_task = Task(
            type=TaskType.IMPORT,
            chronicle_id=chronicle_id,
            data=json.dumps({"file_path": str(second_file), "append": True}),
        )
        await handlers.handle_import(second_task, _noop_progress)

        session = await db_manager.get_project_session(str(chronicle_id))
        async with session:
            repo = SQLiteTranscriptRepository(session)
            lines = await repo.get_lines()

        assert [line.speaker_name for line in lines] == ["Alice", "Bob", "Carol"]
        assert [line.text for line in lines] == ["Hello", "Hi", "Later on"]
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_handle_import_without_append_still_overwrites(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        handlers = WorkerHandlers(db_manager)
        imports_dir = db_manager.get_imports_path()
        chronicle_id = uuid4()

        first_file = imports_dir / "part1.txt"
        first_file.write_text("Alice: Original\n")
        first_task = Task(
            type=TaskType.IMPORT,
            chronicle_id=chronicle_id,
            data=json.dumps({"file_path": str(first_file)}),
        )
        await handlers.handle_import(first_task, _noop_progress)

        second_file = imports_dir / "part2.txt"
        second_file.write_text("Bob: Replacement\n")
        second_task = Task(
            type=TaskType.IMPORT,
            chronicle_id=chronicle_id,
            data=json.dumps({"file_path": str(second_file)}),
        )
        await handlers.handle_import(second_task, _noop_progress)

        session = await db_manager.get_project_session(str(chronicle_id))
        async with session:
            repo = SQLiteTranscriptRepository(session)
            lines = await repo.get_lines()

        assert [line.text for line in lines] == ["Replacement"]
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_handle_clean_backfills_speaker_count_without_retagging(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            chronicle = await chronicle_repo.create(Chronicle(title="Test Chronicle"))

            handlers = WorkerHandlers(db_manager, chronicle_repo=chronicle_repo)
            imports_dir = db_manager.get_imports_path()
            transcript_file = imports_dir / "transcript.txt"
            transcript_file.write_text("Alice: Hello\nAlice: there\nBob: Hi\n")

            import_task = Task(
                type=TaskType.IMPORT,
                chronicle_id=chronicle.id,
                data=json.dumps({"file_path": str(transcript_file)}),
            )
            await handlers.handle_import(import_task, _noop_progress)

            clean_task = Task(type=TaskType.CLEAN, chronicle_id=chronicle.id)
            await handlers.handle_clean(clean_task, _noop_progress)

            updated = await chronicle_repo.get_by_id(chronicle.id)
            assert updated.speakers_count == 2
            # Clean doesn't create a new transcript, so it shouldn't tag again -
            # add_tag is idempotent anyway, but this pins the intent.
            assert [t.name for t in updated.tags] == ["Transcript"]
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_handle_import_logs_parse_count_and_finish(tmp_path, caplog):
    """Regression test: previously the only log line was "Importing transcript
    from..." at the very start - nothing logged how many lines were parsed or that
    the import actually finished.
    """
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        handlers = WorkerHandlers(db_manager)
        imports_dir = db_manager.get_imports_path()
        transcript_file = imports_dir / "transcript.txt"
        transcript_file.write_text("Alice: Hello\nBob: Hi\n")

        chronicle_id = uuid4()
        task = Task(
            type=TaskType.IMPORT,
            chronicle_id=chronicle_id,
            data=json.dumps({"file_path": str(transcript_file)}),
        )

        with caplog.at_level("INFO", logger="chronicler.core.processing.handlers"):
            await handlers.handle_import(task, _noop_progress)

        assert "Parsed 2 lines" in caplog.text
        assert "Transcript import finished" in caplog.text
        assert "2 lines, 2 speakers" in caplog.text
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_handle_clean_logs_line_counts_and_finish(tmp_path, caplog):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        handlers = WorkerHandlers(db_manager)
        imports_dir = db_manager.get_imports_path()
        transcript_file = imports_dir / "transcript.txt"
        transcript_file.write_text("Alice: Hello\nAlice: there\nBob: Hi\n")

        chronicle_id = uuid4()
        import_task = Task(
            type=TaskType.IMPORT,
            chronicle_id=chronicle_id,
            data=json.dumps({"file_path": str(transcript_file)}),
        )
        await handlers.handle_import(import_task, _noop_progress)

        clean_task = Task(type=TaskType.CLEAN, chronicle_id=chronicle_id)
        with caplog.at_level("INFO", logger="chronicler.core.processing.handlers"):
            await handlers.handle_clean(clean_task, _noop_progress)

        assert "Cleaning 3 lines" in caplog.text
        assert "Cleaned down to 2 lines" in caplog.text
        assert "Transcript clean finished" in caplog.text
    finally:
        await db_manager.close_all()


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

            fake_lines = [
                TranscriptLine(text="Hello there", start_time=0.0, end_time=1.0),
                TranscriptLine(text="General Kenobi", start_time=1.0, end_time=2.0),
            ]
            with patch(
                "chronicler.core.processing.transcriber.transcribe_audio",
                return_value=fake_lines,
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
                return_value=[TranscriptLine(text="Hi", start_time=0.0, end_time=90.0)],
            ):
                await handlers.handle_transcribe(alice_task, _noop_progress)

            bob_task, _ = await _make_transcribe_task(db_manager, chronicle.id, "Bob", "bob.mp3")
            with patch(
                "chronicler.core.processing.transcriber.transcribe_audio",
                return_value=[TranscriptLine(text="Hello", start_time=0.0, end_time=30.0)],
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
                return_value=[TranscriptLine(text="Hi", start_time=0.0, end_time=1.0)],
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
                return_value=[
                    TranscriptLine(text="Alice line one", start_time=0.0, end_time=1.0)
                ],
            ):
                await handlers.handle_transcribe(alice_task, _noop_progress)

            bob_task, _ = await _make_transcribe_task(db_manager, chronicle.id, "Bob", "bob.mp3")
            with patch(
                "chronicler.core.processing.transcriber.transcribe_audio",
                return_value=[TranscriptLine(text="Bob line one", start_time=0.5, end_time=1.5)],
            ):
                await handlers.handle_transcribe(bob_task, _noop_progress)

            # Re-transcribe Alice's track (e.g. a corrected re-recording).
            alice_retake_task, _ = await _make_transcribe_task(
                db_manager, chronicle.id, "Alice", "alice_retake.mp3"
            )
            with patch(
                "chronicler.core.processing.transcriber.transcribe_audio",
                return_value=[
                    TranscriptLine(text="Alice corrected line", start_time=0.0, end_time=1.0)
                ],
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
