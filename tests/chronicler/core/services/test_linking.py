"""Tests for linking a project database that lives outside the workspace."""

import pytest

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import TranscriptLine
from chronicler.core.services.chronicle_service import ChronicleService
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.core.sqlite import (
    SQLiteChronicleRepository,
    SQLiteKnownSpeakerRepository,
    SQLiteTranscriptRepository,
)


async def _workspace(tmp_path):
    db_manager = DatabaseManager(tmp_path / "workspace")
    await db_manager.init_archive()
    session = db_manager.get_archive_session()
    chronicles = SQLiteChronicleRepository(session)
    speakers = SQLiteKnownSpeakerRepository(session)
    transcripts = TranscriptService(db_manager, chronicles, speakers)
    service = ChronicleService(chronicles, db_manager, transcripts)
    return db_manager, session, service, transcripts


async def _external_project(db_manager, tmp_path, lines):
    """A project.db somewhere else entirely, with `lines` already in it."""
    directory = tmp_path / "elsewhere" / "campaign-three"
    directory.mkdir(parents=True)
    project_db = directory / "project.db"

    session = await db_manager.get_project_session("staging", custom_path=project_db)
    async with session:
        repo = SQLiteTranscriptRepository(session)
        for line in lines:
            speaker = await repo.get_or_create_speaker(line.speaker_name)
            line.speaker_id = speaker.id
        await repo.add_lines(lines)
        await session.commit()
    return project_db


def _line(speaker, text, start, end):
    return TranscriptLine(speaker_name=speaker, text=text, start_time=start, end_time=end)


class TestHydration:
    @pytest.mark.asyncio
    async def test_it_counts_the_speakers_it_finds(self, tmp_path):
        db_manager, session, service, _ = await _workspace(tmp_path)
        try:
            project_db = await _external_project(
                db_manager,
                tmp_path,
                [_line("Nyx", "We ride at dawn.", 0.0, 3.0), _line("Vale", "Again?", 3.0, 4.5)],
            )

            chronicle = await service.link_external_chronicle(str(project_db))

            assert chronicle.speakers_count == 2
        finally:
            await session.close()
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_it_reads_the_duration_off_the_last_line(self, tmp_path):
        db_manager, session, service, _ = await _workspace(tmp_path)
        try:
            project_db = await _external_project(
                db_manager, tmp_path, [_line("Nyx", "Hello.", 0.0, 3725.0)]
            )

            chronicle = await service.link_external_chronicle(str(project_db))

            assert chronicle.duration == "1h 2m"
        finally:
            await session.close()
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_a_linked_transcript_is_not_still_marked_imported(self, tmp_path):
        db_manager, session, service, _ = await _workspace(tmp_path)
        try:
            project_db = await _external_project(
                db_manager, tmp_path, [_line("Nyx", "Hello.", 0.0, 1.0)]
            )

            chronicle = await service.link_external_chronicle(str(project_db))

            assert chronicle.status == "Transcribed"
        finally:
            await session.close()
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_it_is_tagged_as_a_transcript(self, tmp_path):
        db_manager, session, service, _ = await _workspace(tmp_path)
        try:
            project_db = await _external_project(
                db_manager, tmp_path, [_line("Nyx", "Hello.", 0.0, 1.0)]
            )

            chronicle = await service.link_external_chronicle(str(project_db))
            reloaded = await service.get_chronicle(chronicle.id)

            assert "Transcript" in [tag.name for tag in reloaded.tags]
        finally:
            await session.close()
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_an_empty_project_claims_nothing(self, tmp_path):
        db_manager, session, service, _ = await _workspace(tmp_path)
        try:
            project_db = await _external_project(db_manager, tmp_path, [])

            chronicle = await service.link_external_chronicle(str(project_db))

            assert chronicle.speakers_count == 0
            assert chronicle.duration is None
            assert chronicle.status == "Imported"
        finally:
            await session.close()
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_the_title_comes_from_the_containing_directory(self, tmp_path):
        db_manager, session, service, _ = await _workspace(tmp_path)
        try:
            project_db = await _external_project(db_manager, tmp_path, [])

            chronicle = await service.link_external_chronicle(str(project_db))

            assert chronicle.title == "campaign-three"
        finally:
            await session.close()
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_a_generic_chronicles_directory_is_not_used_as_the_name(self, tmp_path):
        """ "chronicles" is the container directory, not a name worth showing."""
        db_manager, session, service, _ = await _workspace(tmp_path)
        try:
            directory = tmp_path / "elsewhere" / "chronicles"
            directory.mkdir(parents=True)
            project_db = directory / "session-14.db"
            inner = await db_manager.get_project_session("staging2", custom_path=project_db)
            await inner.close()

            chronicle = await service.link_external_chronicle(str(project_db))

            assert chronicle.title == "session-14"
        finally:
            await session.close()
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_the_project_path_is_remembered(self, tmp_path):
        db_manager, session, service, _ = await _workspace(tmp_path)
        try:
            project_db = await _external_project(db_manager, tmp_path, [])

            chronicle = await service.link_external_chronicle(str(project_db))

            assert chronicle.project_path == str(project_db)
        finally:
            await session.close()
            await db_manager.close_all()


class TestSpeakerRegistry:
    @pytest.mark.asyncio
    async def test_linked_speakers_join_the_workspace_registry(self, tmp_path):
        db_manager, session, service, transcripts = await _workspace(tmp_path)
        try:
            project_db = await _external_project(
                db_manager,
                tmp_path,
                [_line("Nyx", "We ride.", 0.0, 1.0), _line("Vale", "Fine.", 1.0, 2.0)],
            )

            await service.link_external_chronicle(str(project_db))

            assert await transcripts.list_known_speakers() == ["Nyx", "Vale"]
        finally:
            await session.close()
            await db_manager.close_all()


class TestExternalSources:
    @pytest.mark.asyncio
    async def test_audio_beside_an_external_project_is_found(self, tmp_path):
        """
        A linked chronicle's audio lives next to its project.db, not in the workspace -
        looking in the workspace made every linked source read as missing.
        """
        db_manager, session, service, transcripts = await _workspace(tmp_path)
        try:
            project_db = await _external_project(db_manager, tmp_path, [])
            sources = project_db.parent / "sources"
            sources.mkdir()
            (sources / "gm.wav").write_bytes(b"audio")

            chronicle = await service.link_external_chronicle(str(project_db))
            found = await transcripts.list_audio_sources(chronicle.id)

            assert [source.filename for source in found] == ["gm.wav"]
            assert found[0].missing is False
        finally:
            await session.close()
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_a_normal_chronicle_still_uses_the_workspace(self, tmp_path):
        db_manager, session, service, transcripts = await _workspace(tmp_path)
        try:
            chronicle = await service.create_chronicle("In the workspace")
            path = db_manager.get_chronicle_sources_path(str(chronicle.id)) / "gm.wav"
            path.write_bytes(b"audio")

            found = await transcripts.list_audio_sources(chronicle.id)

            assert [source.filename for source in found] == ["gm.wav"]
        finally:
            await session.close()
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_a_linked_chronicle_with_no_sources_directory_lists_nothing(self, tmp_path):
        db_manager, session, service, transcripts = await _workspace(tmp_path)
        try:
            project_db = await _external_project(db_manager, tmp_path, [])
            chronicle = await service.link_external_chronicle(str(project_db))

            assert await transcripts.list_audio_sources(chronicle.id) == []
        finally:
            await session.close()
            await db_manager.close_all()
