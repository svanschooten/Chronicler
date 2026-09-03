"""Tests for editing a transcript through the service layer."""

import pytest

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import Chronicle, TranscriptLine
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.core.sqlite import (
    SQLiteChronicleRepository,
    SQLiteKnownSpeakerRepository,
    SQLiteTranscriptRepository,
)


async def _service(tmp_path, lines=2):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    session = db_manager.get_archive_session()
    chronicles = SQLiteChronicleRepository(session)
    chronicle = await chronicles.create(Chronicle(title="Session"))
    await session.commit()

    service = TranscriptService(db_manager, chronicles, SQLiteKnownSpeakerRepository(session))

    project = await db_manager.get_project_session(str(chronicle.id))
    async with project:
        repo = SQLiteTranscriptRepository(project)
        speaker = await repo.get_or_create_speaker("Nyx")
        await repo.add_lines(
            [
                TranscriptLine(
                    speaker_id=speaker.id,
                    text=f"Line {index}",
                    start_time=float(index),
                    end_time=float(index + 1),
                )
                for index in range(lines)
            ]
        )
        await project.commit()

    return db_manager, session, service, chronicle


class TestEditingText:
    @pytest.mark.asyncio
    async def test_a_corrected_word_is_persisted(self, tmp_path):
        db_manager, session, service, chronicle = await _service(tmp_path)
        try:
            original = (await service.get_transcript(chronicle.id))[0]

            await service.update_line(chronicle.id, original.id, text="Corrected wording")

            assert (await service.get_transcript(chronicle.id))[0].text == "Corrected wording"
        finally:
            await session.close()
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_the_edit_survives_a_fresh_read(self, tmp_path):
        """The stub this replaces returned the line and wrote nothing."""
        db_manager, session, service, chronicle = await _service(tmp_path)
        try:
            original = (await service.get_transcript(chronicle.id))[0]
            await service.update_line(chronicle.id, original.id, text="Written to disk")

            reread = await service.get_transcript(chronicle.id)

            assert reread[0].text == "Written to disk"
            assert reread[1].text == "Line 1"
        finally:
            await session.close()
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_timings_are_left_alone(self, tmp_path):
        db_manager, session, service, chronicle = await _service(tmp_path)
        try:
            original = (await service.get_transcript(chronicle.id))[1]

            updated = await service.update_line(chronicle.id, original.id, text="Rewritten")

            assert (updated.start_time, updated.end_time) == (1.0, 2.0)
        finally:
            await session.close()
            await db_manager.close_all()


class TestReassigningASpeaker:
    @pytest.mark.asyncio
    async def test_a_new_name_creates_the_speaker(self, tmp_path):
        db_manager, session, service, chronicle = await _service(tmp_path)
        try:
            original = (await service.get_transcript(chronicle.id))[0]

            updated = await service.update_line(chronicle.id, original.id, speaker_name="Vale")

            assert updated.speaker_name == "Vale"
            assert "Vale" in await service.list_speaker_names(chronicle.id)
        finally:
            await session.close()
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_the_name_joins_the_workspace_registry(self, tmp_path):
        """A name typed while editing should be offered in the next transcribe dialog."""
        db_manager, session, service, chronicle = await _service(tmp_path)
        try:
            original = (await service.get_transcript(chronicle.id))[0]

            await service.update_line(chronicle.id, original.id, speaker_name="Vale")

            assert "Vale" in await service.list_known_speakers()
        finally:
            await session.close()
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_an_existing_name_is_reused_rather_than_duplicated(self, tmp_path):
        db_manager, session, service, chronicle = await _service(tmp_path)
        try:
            lines = await service.get_transcript(chronicle.id)

            await service.update_line(chronicle.id, lines[0].id, speaker_name="Nyx")

            assert await service.list_speaker_names(chronicle.id) == ["Nyx"]
        finally:
            await session.close()
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_text_and_speaker_can_change_together(self, tmp_path):
        db_manager, session, service, chronicle = await _service(tmp_path)
        try:
            original = (await service.get_transcript(chronicle.id))[0]

            updated = await service.update_line(
                chronicle.id, original.id, text="Both at once", speaker_name="Vale"
            )

            assert updated.text == "Both at once"
            assert updated.speaker_name == "Vale"
        finally:
            await session.close()
            await db_manager.close_all()


class TestDeletingALine:
    @pytest.mark.asyncio
    async def test_it_is_removed_from_the_transcript(self, tmp_path):
        db_manager, session, service, chronicle = await _service(tmp_path, lines=3)
        try:
            lines = await service.get_transcript(chronicle.id)

            await service.delete_line(chronicle.id, lines[1].id)

            assert [line.text for line in await service.get_transcript(chronicle.id)] == [
                "Line 0",
                "Line 2",
            ]
        finally:
            await session.close()
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_deleting_an_unknown_line_is_refused(self, tmp_path):
        from uuid import uuid4

        db_manager, session, service, chronicle = await _service(tmp_path)
        try:
            with pytest.raises(KeyError):
                await service.delete_line(chronicle.id, uuid4())
        finally:
            await session.close()
            await db_manager.close_all()


class TestChronicleMetadata:
    @pytest.mark.asyncio
    async def test_removing_the_last_line_of_a_speaker_updates_the_count(self, tmp_path):
        db_manager, session, service, chronicle = await _service(tmp_path)
        try:
            lines = await service.get_transcript(chronicle.id)
            await service.update_line(chronicle.id, lines[0].id, speaker_name="Vale")

            assert await service.refresh_speaker_count(chronicle.id) == 2
        finally:
            await session.close()
            await db_manager.close_all()
