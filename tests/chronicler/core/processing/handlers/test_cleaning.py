"""Tests for the CLEAN task handler."""

import asyncio
import json
import sqlite3
import threading
from contextlib import closing
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import Chronicle, Task, TaskType, TranscriptLine
from chronicler.core.processing.cleaners import TranscriptCleaner
from chronicler.core.processing.handlers import WorkerHandlers
from chronicler.core.processing.handlers.cleaning import CLEAN_ATTEMPTS
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
async def test_handle_clean_keeps_each_lines_track(tmp_path):
    """Cleaning rewrites every line, and must not drop which track each one came from."""
    db_manager = DatabaseManager(tmp_path)
    try:
        handlers = WorkerHandlers(db_manager)
        chronicle_id = uuid4()
        await register_chronicle(db_manager, chronicle_id)
        session = await db_manager.get_project_session(str(chronicle_id))
        async with session:
            repo = SQLiteTranscriptRepository(session)
            sources = SQLiteAudioSourceRepository(session)
            part1 = await sources.register("part1.wav")
            part2 = await sources.register("part2.wav")
            alice = await repo.get_or_create_speaker("Alice")
            await repo.add_lines(
                [
                    TranscriptLine(
                        speaker_id=alice.id,
                        source_id=part1.id,
                        text="One",
                        start_time=0,
                        end_time=1,
                    ),
                    TranscriptLine(
                        speaker_id=alice.id,
                        source_id=part2.id,
                        text="Two",
                        start_time=1,
                        end_time=2,
                    ),
                ]
            )
            await session.commit()

        await handlers.handle_clean(
            Task(type=TaskType.CLEAN, chronicle_id=chronicle_id), _noop_progress
        )

        session = await db_manager.get_project_session(str(chronicle_id))
        async with session:
            lines = await SQLiteTranscriptRepository(session).get_lines()
        assert [(line.text, line.source_id) for line in lines] == [
            ("One", part1.id),
            ("Two", part2.id),
        ]
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

            handlers = WorkerHandlers(db_manager, archive_sessions=db_manager.get_archive_session)
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

            updated = await read_chronicle(db_manager, chronicle.id)
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
                    data=json.dumps({"cleaning": {"strip_patterns": ["(unclosed"]}}),
                ),
                _noop_progress,
            )
    finally:
        await db_manager.close_all()


async def _chronicle_with_lines(db_manager, chronicle_id, *texts, custom_path=None):
    await register_chronicle(db_manager, chronicle_id, custom_path)
    session = await db_manager.get_project_session(str(chronicle_id))
    async with session:
        repo = SQLiteTranscriptRepository(session)
        alice = await repo.get_or_create_speaker("Alice")
        await repo.add_lines(
            [
                TranscriptLine(speaker_id=alice.id, text=text, start_time=i, end_time=i + 1)
                for i, text in enumerate(texts)
            ]
        )
        await session.commit()


def _snapshot_texts(path) -> list[str]:
    with closing(sqlite3.connect(path)) as connection:
        rows = connection.execute("SELECT text FROM transcript_lines ORDER BY start_time")
        return [text for (text,) in rows]


class TestSnapshotBeforeCleaning:
    @pytest.mark.asyncio
    async def test_the_original_lines_are_kept_in_a_snapshot(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        try:
            chronicle_id = uuid4()
            await _chronicle_with_lines(db_manager, chronicle_id, "You.", "We ride at dawn.")

            await WorkerHandlers(db_manager).handle_clean(
                Task(type=TaskType.CLEAN, chronicle_id=chronicle_id), _noop_progress
            )

            snapshots = db_manager.snapshots_path_for(str(chronicle_id))
            (snapshot,) = snapshots.glob("before-clean-*.db")
            assert snapshots == tmp_path / "chronicles" / str(chronicle_id) / "snapshots"
            assert _snapshot_texts(snapshot) == ["You.", "We ride at dawn."]
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_the_oldest_and_the_two_newest_are_kept(self, tmp_path):
        """The oldest holds the transcript before any clean: the copy most worth keeping."""
        db_manager = DatabaseManager(tmp_path)
        try:
            chronicle_id = uuid4()
            await _chronicle_with_lines(db_manager, chronicle_id, "We ride at dawn.")
            handlers = WorkerHandlers(db_manager)

            made = []
            for _ in range(5):
                made.append(await handlers.snapshot_before_clean(chronicle_id))

            kept = sorted(db_manager.snapshots_path_for(str(chronicle_id)).iterdir())
            assert kept == [made[0], made[3], made[4]]
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_a_linked_chronicle_keeps_them_beside_its_database(self, tmp_path):
        db_manager = DatabaseManager(tmp_path / "workspace")
        await db_manager.init_archive()
        try:
            project_db = tmp_path / "elsewhere" / "project.db"
            project_db.parent.mkdir()
            archive_session = db_manager.get_archive_session()
            async with archive_session:
                chronicle_repo = SQLiteChronicleRepository(archive_session)
                chronicle = await chronicle_repo.create(
                    Chronicle(title="Linked", project_path=str(project_db))
                )
                await _chronicle_with_lines(
                    db_manager, chronicle.id, "We ride.", custom_path=project_db
                )

            handlers = WorkerHandlers(db_manager, archive_sessions=db_manager.get_archive_session)
            await handlers.handle_clean(
                Task(type=TaskType.CLEAN, chronicle_id=chronicle.id), _noop_progress
            )

            assert len(list((project_db.parent / "snapshots").glob("before-clean-*.db"))) == 1
            assert not (tmp_path / "workspace" / "chronicles" / str(chronicle.id)).exists()
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_a_linked_file_that_has_moved_fails_without_recreating_it(self, tmp_path):
        """The snapshot used to create an empty database there, which was then "cleaned"."""
        db_manager = DatabaseManager(tmp_path / "workspace")
        await db_manager.init_archive()
        try:
            gone = tmp_path / "gone" / "project.db"
            async with db_manager.get_archive_session() as session:
                chronicle = await SQLiteChronicleRepository(session).create(
                    Chronicle(title="Moved", project_path=str(gone))
                )

            handlers = WorkerHandlers(db_manager, archive_sessions=db_manager.get_archive_session)
            with pytest.raises(FileNotFoundError):
                await handlers.handle_clean(
                    Task(type=TaskType.CLEAN, chronicle_id=chronicle.id), _noop_progress
                )

            assert not gone.parent.exists()
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_chronicles_sharing_a_folder_keep_their_own_snapshots(self, tmp_path):
        """Two linked databases in one folder share `snapshots/`; pruning stays per chronicle."""
        db_manager = DatabaseManager(tmp_path / "workspace")
        await db_manager.init_archive()
        try:
            folder = tmp_path / "campaigns"
            folder.mkdir()
            ids = []
            async with db_manager.get_archive_session() as archive_session:
                chronicles = SQLiteChronicleRepository(archive_session)
                for name in ("one", "two"):
                    chronicle = await chronicles.create(
                        Chronicle(title=name, project_path=str(folder / f"{name}.db"))
                    )
                    await _chronicle_with_lines(
                        db_manager, chronicle.id, "We ride.", custom_path=folder / f"{name}.db"
                    )
                    ids.append(chronicle.id)

            handlers = WorkerHandlers(db_manager, archive_sessions=db_manager.get_archive_session)
            first = await handlers.snapshot_before_clean(ids[0])
            for _ in range(5):
                await handlers.snapshot_before_clean(ids[1])

            snapshots = list((folder / "snapshots").iterdir())
            assert first in snapshots
            assert len([path for path in snapshots if str(ids[1]) in path.name]) == 3
        finally:
            await db_manager.close_all()


class TestCleaningOutsideTheTransaction:
    """A slow clean holds no lock, and an edit made while it runs is not overwritten."""

    @staticmethod
    async def _edit_first_line(db_manager, chronicle_id, text):
        async with db_manager.transaction(chronicle_id) as session:
            repo = SQLiteTranscriptRepository(session)
            first = (await repo.get_lines())[0]
            await repo.update_line(first.id, text=text)

    @pytest.mark.asyncio
    async def test_an_edit_while_cleaning_runs_is_kept_and_cleaned(self, tmp_path):
        # A short busy timeout: the edit fails fast if the clean still holds a lock.
        db_manager = DatabaseManager(tmp_path, busy_timeout=0.2)
        try:
            chronicle_id = uuid4()
            await _chronicle_with_lines(db_manager, chronicle_id, "We ride.", "At dawn.")

            started, release = threading.Event(), threading.Event()
            calls = []
            real_clean = TranscriptCleaner.clean

            def slow_clean(self, lines):
                calls.append([line.text for line in lines])
                if len(calls) == 1:
                    started.set()
                    release.wait(5)
                return real_clean(self, lines)

            with patch.object(TranscriptCleaner, "clean", slow_clean):
                cleaning = asyncio.create_task(
                    WorkerHandlers(db_manager).handle_clean(
                        Task(type=TaskType.CLEAN, chronicle_id=chronicle_id), _noop_progress
                    )
                )
                await asyncio.to_thread(started.wait, 5)
                await self._edit_first_line(db_manager, chronicle_id, "We   ride  together.")
                release.set()
                await cleaning

            assert calls[1][0] == "We   ride  together."
            assert len(calls) == 2
            # Cleaned from the edited text: whitespace collapsed, one speaker's lines merged.
            assert await _texts(db_manager, chronicle_id) == ["We ride together. At dawn."]
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_a_transcript_that_never_settles_fails_the_clean_unchanged(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        try:
            chronicle_id = uuid4()
            await _chronicle_with_lines(db_manager, chronicle_id, "We ride.")
            loop = asyncio.get_running_loop()
            edits = []
            real_clean = TranscriptCleaner.clean

            def clean_while_editing(self, lines):
                edit = f"edit {len(edits)}"
                edits.append(edit)
                asyncio.run_coroutine_threadsafe(
                    TestCleaningOutsideTheTransaction._edit_first_line(
                        db_manager, chronicle_id, edit
                    ),
                    loop,
                ).result(5)
                return real_clean(self, lines)

            with patch.object(TranscriptCleaner, "clean", clean_while_editing):
                with pytest.raises(RuntimeError, match="kept changing"):
                    await WorkerHandlers(db_manager).handle_clean(
                        Task(type=TaskType.CLEAN, chronicle_id=chronicle_id), _noop_progress
                    )

            assert len(edits) == CLEAN_ATTEMPTS
            assert await _texts(db_manager, chronicle_id) == [edits[-1]]
        finally:
            await db_manager.close_all()
