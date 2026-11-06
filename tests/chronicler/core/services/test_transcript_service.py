"""Tests for TranscriptService - reading, speaker bookkeeping and audio sources."""

import pytest

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import Chronicle, TranscriptLine
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.core.sqlite import (
    SQLiteAudioSourceRepository,
    SQLiteChronicleRepository,
    SQLiteTranscriptRepository,
)


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
async def test_delete_track_lines_removes_only_that_tracks_lines(tmp_path):
    """
    Re-transcribing one track must leave every other track alone, including another
    track for the same speaker.
    """
    db_manager = DatabaseManager(tmp_path)
    try:
        session = await db_manager.get_project_session("chronicle-1")
        async with session:
            repo = SQLiteTranscriptRepository(session)
            sources = SQLiteAudioSourceRepository(session)
            part1 = await sources.register("part1.wav")
            part2 = await sources.register("part2.wav")
            alice = await repo.get_or_create_speaker("Alice")
            await repo.add_lines(
                [
                    TranscriptLine(
                        speaker_id=alice.id, source_id=part1.id, start_time=0, end_time=1, text="1"
                    ),
                    TranscriptLine(
                        speaker_id=alice.id, source_id=part2.id, start_time=1, end_time=2, text="2"
                    ),
                    TranscriptLine(speaker_id=alice.id, start_time=2, end_time=3, text="untracked"),
                ]
            )
            await session.commit()

            await repo.delete_track_lines(part1.id)
            await session.commit()
            assert [line.text for line in await repo.get_lines()] == ["2", "untracked"]

            await repo.delete_track_lines(part2.id)
            await session.commit()
            assert [line.text for line in await repo.get_lines()] == ["untracked"]
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


async def _service(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    session = db_manager.get_archive_session()
    return db_manager, session, TranscriptService(db_manager, SQLiteChronicleRepository(session))


@pytest.mark.asyncio
async def test_reading_an_unknown_chronicle_raises_and_creates_nothing(tmp_path):
    from uuid import uuid4

    db_manager, session, service = await _service(tmp_path)
    try:
        unknown = uuid4()

        with pytest.raises(LookupError):
            await service.get_transcript(unknown)
        with pytest.raises(LookupError):
            await service.list_audio_sources(unknown)

        assert not (tmp_path / "chronicles" / str(unknown)).exists()
    finally:
        await session.close()
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_a_known_chronicle_gets_its_database_on_first_use(tmp_path):
    db_manager, session, service = await _service(tmp_path)
    try:
        chronicle = await SQLiteChronicleRepository(session).create(Chronicle(title="New"))
        await session.commit()

        assert await service.get_transcript(chronicle.id) == []
        assert (tmp_path / "chronicles" / str(chronicle.id) / "project.db").exists()
    finally:
        await session.close()
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_a_linked_chronicle_whose_file_moved_raises_instead_of_starting_a_new_one(tmp_path):
    db_manager, session, service = await _service(tmp_path)
    try:
        gone = tmp_path / "elsewhere" / "project.db"
        chronicle = await SQLiteChronicleRepository(session).create(
            Chronicle(title="Linked", project_path=str(gone))
        )
        await session.commit()

        with pytest.raises(FileNotFoundError):
            await service.get_transcript(chronicle.id)

        assert not gone.parent.exists()
    finally:
        await session.close()
        await db_manager.close_all()
