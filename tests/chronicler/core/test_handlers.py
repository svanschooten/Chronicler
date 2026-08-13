import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import Task, TaskType
from chronicler.core.processing.handlers import WorkerHandlers
from chronicler.core.sqlite import SQLiteTranscriptRepository


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
