"""Tests for the IMPORT task handler."""

import json
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import Chronicle, Task, TaskType
from chronicler.core.processing.handlers import WorkerHandlers
from chronicler.core.processing.importers import RegexImporter
from chronicler.core.sqlite import SQLiteChronicleRepository, SQLiteTranscriptRepository


async def _noop_progress(_progress: int) -> None:
    pass


@pytest.mark.asyncio
async def test_handle_import_rejects_file_path_outside_imports_dir(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        handlers = WorkerHandlers(db_manager)

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
async def test_handle_import_logs_parse_count_and_finish(tmp_path, caplog):
    """
    Regression test: previously the only log line was "Importing transcript from..." at the
    very start - nothing logged how many lines were parsed or that the import actually
    finished.
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
async def test_handle_import_append_hands_the_offset_to_the_importer(tmp_path):
    """
    Where an appended file starts on the chronicle's timeline is known before a single line
    is parsed - so it's a parse-time input, not a shift applied to every line after the
    fact.
    """
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        handlers = WorkerHandlers(db_manager)
        imports_dir = db_manager.get_imports_path()
        chronicle_id = uuid4()

        first_file = imports_dir / "part1.txt"
        first_file.write_text("Alice: Hello\nBob: Hi\n")
        await handlers.handle_import(
            Task(
                type=TaskType.IMPORT,
                chronicle_id=chronicle_id,
                data=json.dumps({"file_path": str(first_file)}),
            ),
            _noop_progress,
        )

        second_file = imports_dir / "part2.txt"
        second_file.write_text("Carol: Later on\n")
        second_task = Task(
            type=TaskType.IMPORT,
            chronicle_id=chronicle_id,
            data=json.dumps({"file_path": str(second_file), "append": True}),
        )

        seen: dict[str, float] = {}
        real_parse = RegexImporter.parse

        def _spy(self: Any, content: Any, start_offset: float = 0.0) -> Any:
            seen["start_offset"] = start_offset
            return real_parse(self, content, start_offset=start_offset)

        with patch.object(RegexImporter, "parse", _spy):
            await handlers.handle_import(second_task, _noop_progress)

        assert seen["start_offset"] == 2.0

        session = await db_manager.get_project_session(str(chronicle_id))
        async with session:
            repo = SQLiteTranscriptRepository(session)
            lines = await repo.get_lines()

        assert [line.start_time for line in lines] == [0.0, 1.0, 2.0]
        assert [line.end_time for line in lines] == [1.0, 2.0, 3.0]
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_handle_import_without_append_parses_from_zero(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    try:
        handlers = WorkerHandlers(db_manager)
        imports_dir = db_manager.get_imports_path()
        chronicle_id = uuid4()

        first_file = imports_dir / "part1.txt"
        first_file.write_text("Alice: Hello\nBob: Hi\n")
        await handlers.handle_import(
            Task(
                type=TaskType.IMPORT,
                chronicle_id=chronicle_id,
                data=json.dumps({"file_path": str(first_file)}),
            ),
            _noop_progress,
        )

        second_file = imports_dir / "part2.txt"
        second_file.write_text("Carol: Replacement\n")
        await handlers.handle_import(
            Task(
                type=TaskType.IMPORT,
                chronicle_id=chronicle_id,
                data=json.dumps({"file_path": str(second_file)}),
            ),
            _noop_progress,
        )

        session = await db_manager.get_project_session(str(chronicle_id))
        async with session:
            repo = SQLiteTranscriptRepository(session)
            lines = await repo.get_lines()

        assert [(line.start_time, line.end_time) for line in lines] == [(0.0, 1.0)]
    finally:
        await db_manager.close_all()
