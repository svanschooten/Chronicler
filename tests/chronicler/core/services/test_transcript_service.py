"""Tests for TranscriptService - reading, speaker bookkeeping and audio sources."""

import pytest

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import Chronicle, TranscriptLine
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.core.sqlite import SQLiteChronicleRepository, SQLiteTranscriptRepository


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
async def test_delete_lines_by_speaker_leaves_other_speakers_untouched(tmp_path):
    """
    The concrete requirement behind re-transcribing a single-speaker audio source:
    overwriting one speaker's track must not wipe another speaker's lines the way
    delete_all_lines() would.
    """
    db_manager = DatabaseManager(tmp_path)
    try:
        session = await db_manager.get_project_session("chronicle-1")
        async with session:
            repo = SQLiteTranscriptRepository(session)
            alice = await repo.get_or_create_speaker("Alice")
            bob = await repo.get_or_create_speaker("Bob")
            await repo.add_lines(
                [
                    TranscriptLine(speaker_id=alice.id, start_time=0.0, end_time=1.0, text="Hi"),
                    TranscriptLine(speaker_id=bob.id, start_time=0.5, end_time=1.5, text="Hello"),
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
