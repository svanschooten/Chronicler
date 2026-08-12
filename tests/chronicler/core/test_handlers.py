import json
from uuid import uuid4

import pytest

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import Task, TaskType
from chronicler.core.processing.handlers import WorkerHandlers


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
            from chronicler.core.sqlite import SQLiteTranscriptRepository

            repo = SQLiteTranscriptRepository(session)
            lines = await repo.get_lines()
            assert len(lines) == 2
    finally:
        await db_manager.close_all()
