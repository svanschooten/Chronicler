"""Tests for editing individual transcript lines."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from chronicler.core.models import TranscriptLine
from chronicler.core.project_database import ProjectBase
from chronicler.core.sqlite import SQLiteTranscriptRepository


@pytest_asyncio.fixture
async def repository():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(ProjectBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield SQLiteTranscriptRepository(session)
    await engine.dispose()


async def _seed(repository, count=3):
    lines = []
    for index in range(count):
        speaker = await repository.get_or_create_speaker(f"Speaker {index}")
        lines.append(
            TranscriptLine(
                speaker_id=speaker.id,
                text=f"Line {index}",
                start_time=float(index),
                end_time=float(index + 1),
            )
        )
    await repository.add_lines(lines)
    return lines


class TestUpdatingALine:
    @pytest.mark.asyncio
    async def test_the_text_is_replaced(self, repository):
        lines = await _seed(repository)

        updated = await repository.update_line(lines[1].id, text="Corrected wording")

        assert updated.text == "Corrected wording"
        assert (await repository.get_lines())[1].text == "Corrected wording"

    @pytest.mark.asyncio
    async def test_the_speaker_can_be_reassigned(self, repository):
        lines = await _seed(repository)
        other = await repository.get_or_create_speaker("Someone Else")

        updated = await repository.update_line(lines[0].id, speaker_id=other.id)

        assert updated.speaker_id == other.id
        assert updated.speaker_name == "Someone Else"

    @pytest.mark.asyncio
    async def test_timings_survive_a_text_edit(self, repository):
        """Editing a word must not shift the line off the audio it came from."""
        lines = await _seed(repository)

        updated = await repository.update_line(lines[2].id, text="Rewritten")

        assert updated.start_time == 2.0
        assert updated.end_time == 3.0

    @pytest.mark.asyncio
    async def test_only_what_is_passed_changes(self, repository):
        lines = await _seed(repository)

        updated = await repository.update_line(lines[0].id, text="New text")

        assert updated.speaker_name == "Speaker 0"

    @pytest.mark.asyncio
    async def test_an_unknown_line_is_a_key_error(self, repository):
        from uuid import uuid4

        with pytest.raises(KeyError):
            await repository.update_line(uuid4(), text="nothing to update")

    @pytest.mark.asyncio
    async def test_the_other_lines_are_untouched(self, repository):
        lines = await _seed(repository)

        await repository.update_line(lines[1].id, text="Only this one")

        texts = [line.text for line in await repository.get_lines()]
        assert texts == ["Line 0", "Only this one", "Line 2"]


class TestDeletingALine:
    @pytest.mark.asyncio
    async def test_it_is_gone(self, repository):
        lines = await _seed(repository)

        await repository.delete_line(lines[1].id)

        assert [line.text for line in await repository.get_lines()] == ["Line 0", "Line 2"]

    @pytest.mark.asyncio
    async def test_deleting_an_unknown_line_is_a_key_error(self, repository):
        from uuid import uuid4

        await _seed(repository)

        with pytest.raises(KeyError):
            await repository.delete_line(uuid4())

    @pytest.mark.asyncio
    async def test_the_speaker_survives_its_last_line(self, repository):
        """A speaker row outliving its lines keeps the source-to-speaker mapping intact."""
        lines = await _seed(repository, count=1)

        await repository.delete_line(lines[0].id)

        assert [speaker.name for speaker in await repository.get_speakers()] == ["Speaker 0"]
