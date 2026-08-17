"""Tests for the CLEAN task handler.

Cleaning operates on lines that are already in a project database, so these tests
seed one by running a real import first rather than writing rows by hand - that keeps
what's being cleaned identical in shape to what the app actually produces.
"""

import json
from uuid import uuid4

import pytest

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import Chronicle, Task, TaskType
from chronicler.core.processing.handlers import WorkerHandlers
from chronicler.core.sqlite import SQLiteChronicleRepository, SQLiteTranscriptRepository


async def _noop_progress(_progress: int) -> None:
    pass


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
