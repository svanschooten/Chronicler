import pytest

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import Chronicle, TranscriptLine
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.core.sqlite import SQLiteChronicleRepository, SQLiteTranscriptRepository


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
