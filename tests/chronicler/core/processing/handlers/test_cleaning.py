"""Tests for the CLEAN task handler."""

import json
from typing import Any
from unittest.mock import patch
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
    """
    Regression test: delete_all() used to wipe DBSpeaker too, so get_or_create_speaker()
    never found an existing speaker after a clean - every clean run assigned fresh speaker
    ids. delete_all_lines() must not repeat that.
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
        await handlers.handle_clean(clean_task, _noop_progress)

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


@pytest.mark.asyncio
async def test_handle_clean_reuses_the_speaker_ids_already_on_the_lines(tmp_path):
    """
    Cleaning reads its lines straight out of the project database, so every one of them
    already carries a resolved speaker_id.
    """
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

        session = await db_manager.get_project_session(str(chronicle_id))
        async with session:
            repo = SQLiteTranscriptRepository(session)
            ids_before = {line.speaker_name: line.speaker_id for line in await repo.get_lines()}

        looked_up: list[str] = []
        real_get_or_create = SQLiteTranscriptRepository.get_or_create_speaker

        async def _spy(self: Any, name: str) -> Any:
            looked_up.append(name)
            return await real_get_or_create(self, name)

        clean_task = Task(type=TaskType.CLEAN, chronicle_id=chronicle_id)
        with patch.object(SQLiteTranscriptRepository, "get_or_create_speaker", _spy):
            await handlers.handle_clean(clean_task, _noop_progress)

        assert looked_up == []

        session = await db_manager.get_project_session(str(chronicle_id))
        async with session:
            repo = SQLiteTranscriptRepository(session)
            ids_after = {line.speaker_name: line.speaker_id for line in await repo.get_lines()}

        assert ids_after == ids_before
    finally:
        await db_manager.close_all()


async def _import_lines(handlers, chronicle_id, db_manager, text):
    transcript_file = db_manager.get_imports_path() / f"{uuid4().hex}.txt"
    transcript_file.write_text(text)
    await handlers.handle_import(
        Task(
            type=TaskType.IMPORT,
            chronicle_id=chronicle_id,
            data=json.dumps({"file_path": str(transcript_file)}),
        ),
        _noop_progress,
    )


async def _texts(db_manager, chronicle_id):
    session = await db_manager.get_project_session(str(chronicle_id))
    async with session:
        return [line.text for line in await SQLiteTranscriptRepository(session).get_lines()]


@pytest.mark.asyncio
async def test_handle_clean_uses_the_configured_hallucination_phrases(tmp_path):
    from chronicler.core.config import Settings

    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        settings = Settings()
        settings.cleaning.hallucination_phrases = ["Ondertiteling door"]
        settings.cleaning.merge_same_speaker = False
        handlers = WorkerHandlers(db_manager, settings=settings)

        chronicle_id = uuid4()
        await _import_lines(
            handlers,
            chronicle_id,
            db_manager,
            "Alice: Real content\nAlice: Ondertiteling door\nAlice: More content\n",
        )

        await handlers.handle_clean(
            Task(type=TaskType.CLEAN, chronicle_id=chronicle_id), _noop_progress
        )

        assert await _texts(db_manager, chronicle_id) == ["Real content", "More content"]
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_handle_clean_accepts_a_per_task_override(tmp_path):
    from chronicler.core.config import Settings

    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        settings = Settings()
        settings.cleaning.merge_same_speaker = False
        handlers = WorkerHandlers(db_manager, settings=settings)

        chronicle_id = uuid4()
        await _import_lines(
            handlers, chronicle_id, db_manager, "Alice: Keep this\nAlice: Drop this\n"
        )

        await handlers.handle_clean(
            Task(
                type=TaskType.CLEAN,
                chronicle_id=chronicle_id,
                data=json.dumps(
                    {
                        "cleaning": {
                            "hallucination_phrases": ["Drop this"],
                            "merge_same_speaker": False,
                        }
                    }
                ),
            ),
            _noop_progress,
        )

        assert await _texts(db_manager, chronicle_id) == ["Keep this"]
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_handle_clean_rejects_an_unsafe_override_pattern(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        handlers = WorkerHandlers(db_manager)
        chronicle_id = uuid4()
        await _import_lines(handlers, chronicle_id, db_manager, "Alice: Hello\n")

        with pytest.raises(ValueError):
            await handlers.handle_clean(
                Task(
                    type=TaskType.CLEAN,
                    chronicle_id=chronicle_id,
                    data=json.dumps({"cleaning": {"strip_patterns": ["(a+)+$"]}}),
                ),
                _noop_progress,
            )
    finally:
        await db_manager.close_all()
