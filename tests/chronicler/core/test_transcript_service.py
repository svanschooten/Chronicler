import json
from pathlib import Path

import pytest

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import Chronicle, Task, TaskType, TranscriptLine
from chronicler.core.processing.handlers import WorkerHandlers
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.core.sqlite import SQLiteChronicleRepository, SQLiteTranscriptRepository

EXAMPLES_DIR = Path(__file__).resolve().parents[3] / "examples"


async def _noop_progress(_progress: int) -> None:
    pass


@pytest.mark.asyncio
async def test_get_transcript_reads_from_the_chronicles_project_db(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    try:
        await db_manager.init_archive()

        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            chronicle = await chronicle_repo.create(Chronicle(title="Session One"))

        # Write directly into the chronicle's project.db, independent of the service.
        project_session = await db_manager.get_project_session(str(chronicle.id))
        async with project_session:
            repo = SQLiteTranscriptRepository(project_session)
            speaker = await repo.get_or_create_speaker("Alice")
            await repo.add_line(
                TranscriptLine(speaker_id=speaker.id, start_time=0.0, end_time=1.0, text="Hi")
            )
            await project_session.commit()

        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            service = TranscriptService(db_manager, chronicle_repo)
            lines = await service.get_transcript(chronicle.id)

        assert len(lines) == 1
        assert lines[0].text == "Hi"
        assert lines[0].speaker_name == "Alice"
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_get_transcript_uses_custom_project_path_for_linked_chronicles(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    try:
        await db_manager.init_archive()

        external_db = tmp_path / "external" / "project.db"

        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            chronicle = await chronicle_repo.create(
                Chronicle(title="Linked", project_path=str(external_db))
            )

        # Write into the *external* path, not the default workspace/chronicles/<id> one.
        external_session = await db_manager.get_project_session(
            str(chronicle.id), custom_path=external_db
        )
        async with external_session:
            repo = SQLiteTranscriptRepository(external_session)
            speaker = await repo.get_or_create_speaker("Bob")
            await repo.add_line(
                TranscriptLine(speaker_id=speaker.id, start_time=0.0, end_time=1.0, text="Yo")
            )
            await external_session.commit()

        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            service = TranscriptService(db_manager, chronicle_repo)
            lines = await service.get_transcript(chronicle.id)

        assert len(lines) == 1
        assert lines[0].text == "Yo"
        default_path = tmp_path / "chronicles" / str(chronicle.id) / "project.db"
        assert not default_path.exists()
        assert external_db.exists()
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_update_line_does_not_persist_yet(tmp_path):
    """Not implemented yet (Sprint 4) - documents the current, deliberate no-op."""
    db_manager = DatabaseManager(tmp_path)
    try:
        await db_manager.init_archive()

        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            chronicle = await chronicle_repo.create(Chronicle(title="Untouched"))
            service = TranscriptService(db_manager, chronicle_repo)

            line = TranscriptLine(start_time=0.0, end_time=1.0, text="edited")
            result = await service.update_line(chronicle.id, line)

        assert result is line
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_refresh_speaker_count_backfills_from_project_db(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    try:
        await db_manager.init_archive()

        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            chronicle = await chronicle_repo.create(Chronicle(title="Untagged"))
            assert chronicle.speakers_count == 0

        project_session = await db_manager.get_project_session(str(chronicle.id))
        async with project_session:
            repo = SQLiteTranscriptRepository(project_session)
            await repo.get_or_create_speaker("Alice")
            await repo.get_or_create_speaker("Bob")
            await project_session.commit()

        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            service = TranscriptService(db_manager, chronicle_repo)
            count = await service.refresh_speaker_count(chronicle.id)

            assert count == 2
            updated = await chronicle_repo.get_by_id(chronicle.id)
            assert updated.speakers_count == 2
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_export_plaintext_preserves_raw_turn_structure_from_real_example(tmp_path):
    """The concrete acceptance test for the plaintext export format, pinned to a
    real excerpt of examples/example_transcript_001.txt (not hand-written): a
    multi-line speaker turn ("Maldal" spanning 5 original lines) must come out as
    separate indented lines under a padded, colon-aligned speaker column - not
    flattened into one wrapped paragraph. Import only (no Clean): RegexImporter now
    joins a turn's original lines with "\\n" rather than " " specifically so this
    structure survives into the export (see importers.py).
    """
    db_manager = DatabaseManager(tmp_path)
    try:
        await db_manager.init_archive()

        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            chronicle = await chronicle_repo.create(Chronicle(title="Example"))

        handlers = WorkerHandlers(db_manager)
        staged_file = db_manager.get_imports_path() / "example_transcript_001.txt"
        staged_file.write_text((EXAMPLES_DIR / "example_transcript_001.txt").read_text())

        import_task = Task(
            type=TaskType.IMPORT,
            chronicle_id=chronicle.id,
            data=json.dumps({"file_path": str(staged_file)}),
        )
        await handlers.handle_import(import_task, _noop_progress)

        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            service = TranscriptService(db_manager, chronicle_repo)
            exported = await service.export_plaintext(chronicle.id)

        assert (
            "Maldal: I want to say Raveneer, but the other wizard.\n"
            "Ahzek : Windrider?\n"
            "Sergus: Yes.\n"
            "        I think we left one at least.\n"
            "Maldal: Yeah.\n"
            "GM    : What kind of?\n"
            "        Thank you.\n"
            "Maldal: Mordecai men.\n"
            "        Yes.\n"
            "        Couldn't.\n"
            "        Didn't they say that they could power the batteries for us?\n"
            "        I\n"
            "Ahzek : Did we leave some with him?"
        ) in exported
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_export_plaintext_pads_speaker_column_to_longest_name(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    try:
        await db_manager.init_archive()

        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            chronicle = await chronicle_repo.create(Chronicle(title="Padding"))

        project_session = await db_manager.get_project_session(str(chronicle.id))
        async with project_session:
            repo = SQLiteTranscriptRepository(project_session)
            gm = await repo.get_or_create_speaker("GM")
            longhand = await repo.get_or_create_speaker("Longhand")
            await repo.add_lines(
                [
                    TranscriptLine(speaker_id=gm.id, start_time=0.0, end_time=1.0, text="Hi"),
                    TranscriptLine(
                        speaker_id=longhand.id, start_time=1.0, end_time=2.0, text="Hello"
                    ),
                ]
            )
            await project_session.commit()

        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            service = TranscriptService(db_manager, chronicle_repo)
            exported = await service.export_plaintext(chronicle.id)

        assert exported == "GM      : Hi\nLonghand: Hello"
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_export_plaintext_omits_timestamps_by_default(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    try:
        await db_manager.init_archive()

        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            chronicle = await chronicle_repo.create(Chronicle(title="No timestamps"))

        project_session = await db_manager.get_project_session(str(chronicle.id))
        async with project_session:
            repo = SQLiteTranscriptRepository(project_session)
            gm = await repo.get_or_create_speaker("GM")
            await repo.add_line(
                TranscriptLine(speaker_id=gm.id, start_time=65.0, end_time=70.0, text="Hi")
            )
            await project_session.commit()

        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            service = TranscriptService(db_manager, chronicle_repo)
            exported = await service.export_plaintext(chronicle.id)

        assert exported == "GM: Hi"
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_export_plaintext_with_timestamps_prefixes_and_aligns(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    try:
        await db_manager.init_archive()

        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            chronicle = await chronicle_repo.create(Chronicle(title="Timestamped"))

        project_session = await db_manager.get_project_session(str(chronicle.id))
        async with project_session:
            repo = SQLiteTranscriptRepository(project_session)
            gm = await repo.get_or_create_speaker("GM")
            longhand = await repo.get_or_create_speaker("Longhand")
            await repo.add_lines(
                [
                    TranscriptLine(
                        speaker_id=gm.id, start_time=65.0, end_time=66.0, text="Hi"
                    ),
                    TranscriptLine(
                        speaker_id=longhand.id,
                        start_time=70.0,
                        end_time=71.0,
                        text="Hello there\nHow are you",
                    ),
                ]
            )
            await project_session.commit()

        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            service = TranscriptService(db_manager, chronicle_repo)
            exported = await service.export_plaintext(chronicle.id, include_timestamps=True)

        assert exported == (
            "[00:01:05] GM      : Hi\n"
            "[00:01:10] Longhand: Hello there\n"
            "                     How are you"
        )
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_export_plaintext_wraps_long_merged_lines_with_hanging_indent(tmp_path):
    """A Cleaned turn has no "\\n" of its own (TranscriptCleaner flattens whitespace
    when merging consecutive same-speaker lines) - a single long line like that must
    still wrap at PLAINTEXT_EXPORT_WIDTH, hanging-indented under the padded speaker
    column, rather than exporting as one unreadably long physical line.
    """
    db_manager = DatabaseManager(tmp_path)
    try:
        await db_manager.init_archive()

        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            chronicle = await chronicle_repo.create(Chronicle(title="Wrapping"))

        long_text = " ".join(["word"] * 40)
        project_session = await db_manager.get_project_session(str(chronicle.id))
        async with project_session:
            repo = SQLiteTranscriptRepository(project_session)
            speaker = await repo.get_or_create_speaker("GM")
            await repo.add_line(
                TranscriptLine(
                    speaker_id=speaker.id, start_time=0.0, end_time=1.0, text=long_text
                )
            )
            await project_session.commit()

        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            service = TranscriptService(db_manager, chronicle_repo)
            exported = await service.export_plaintext(chronicle.id)

        exported_lines = exported.splitlines()
        assert len(exported_lines) > 1
        assert exported_lines[0].startswith("GM: ")
        assert exported_lines[1].startswith("    ")  # hanging indent, no "GM: " repeat
        assert all(len(line) <= 140 for line in exported_lines)
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_export_plaintext_drops_blank_lines(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    try:
        await db_manager.init_archive()

        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            chronicle = await chronicle_repo.create(Chronicle(title="Blanks"))

        project_session = await db_manager.get_project_session(str(chronicle.id))
        async with project_session:
            repo = SQLiteTranscriptRepository(project_session)
            speaker = await repo.get_or_create_speaker("GM")
            await repo.add_lines(
                [
                    TranscriptLine(speaker_id=speaker.id, start_time=0.0, end_time=1.0, text="Hi"),
                    TranscriptLine(
                        speaker_id=speaker.id, start_time=1.0, end_time=2.0, text="   "
                    ),
                ]
            )
            await project_session.commit()

        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            service = TranscriptService(db_manager, chronicle_repo)
            exported = await service.export_plaintext(chronicle.id)

        assert exported == "GM: Hi"
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_delete_lines_by_speaker_leaves_other_speakers_untouched(tmp_path):
    """The concrete requirement behind re-transcribing a single-speaker audio
    source: overwriting one speaker's track must not wipe another speaker's lines
    the way delete_all_lines() would."""
    db_manager = DatabaseManager(tmp_path)
    try:
        session = await db_manager.get_project_session("chronicle-1")
        async with session:
            repo = SQLiteTranscriptRepository(session)
            alice = await repo.get_or_create_speaker("Alice")
            bob = await repo.get_or_create_speaker("Bob")
            await repo.add_lines(
                [
                    TranscriptLine(
                        speaker_id=alice.id, start_time=0.0, end_time=1.0, text="Hi"
                    ),
                    TranscriptLine(
                        speaker_id=bob.id, start_time=0.5, end_time=1.5, text="Hello"
                    ),
                ]
            )
            await session.commit()

            await repo.delete_lines_by_speaker(alice.id)
            await session.commit()

            remaining = await repo.get_lines()
            assert [line.text for line in remaining] == ["Hello"]
            assert remaining[0].speaker_name == "Bob"
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_list_audio_sources_lists_files_in_chronicle_sources_dir(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    try:
        await db_manager.init_archive()

        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            chronicle = await chronicle_repo.create(Chronicle(title="Podcast"))

        sources_dir = db_manager.get_chronicle_sources_path(str(chronicle.id))
        (sources_dir / "bob.mp3").write_bytes(b"x")
        (sources_dir / "alice.mp3").write_bytes(b"x")

        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            service = TranscriptService(db_manager, chronicle_repo)
            sources = await service.list_audio_sources(chronicle.id)

        assert sources == [str(sources_dir / "alice.mp3"), str(sources_dir / "bob.mp3")]
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_list_audio_sources_empty_when_no_sources_dir_yet(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    try:
        await db_manager.init_archive()

        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            chronicle = await chronicle_repo.create(Chronicle(title="Empty"))
            service = TranscriptService(db_manager, chronicle_repo)
            sources = await service.list_audio_sources(chronicle.id)

        assert sources == []
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_list_speaker_names_returns_sorted_names(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    try:
        await db_manager.init_archive()

        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            chronicle = await chronicle_repo.create(Chronicle(title="Podcast"))

        project_session = await db_manager.get_project_session(str(chronicle.id))
        async with project_session:
            repo = SQLiteTranscriptRepository(project_session)
            await repo.get_or_create_speaker("Bob")
            await repo.get_or_create_speaker("Alice")
            await project_session.commit()

        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle_repo = SQLiteChronicleRepository(archive_session)
            service = TranscriptService(db_manager, chronicle_repo)
            names = await service.list_speaker_names(chronicle.id)

        assert names == ["Alice", "Bob"]
    finally:
        await db_manager.close_all()
