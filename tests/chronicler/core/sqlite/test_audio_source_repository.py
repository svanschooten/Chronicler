from datetime import datetime

import pytest
import pytest_asyncio

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import SourceState
from chronicler.core.sqlite import SQLiteAudioSourceRepository, SQLiteTranscriptRepository


@pytest_asyncio.fixture
async def repo(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    session = await db_manager.get_project_session("chronicle-1")
    try:
        yield SQLiteAudioSourceRepository(session), session
    finally:
        await session.close()
        await db_manager.close_all()


class TestRegister:
    @pytest.mark.asyncio
    async def test_registers_a_new_source(self, repo):
        repository, session = repo

        source = await repository.register("gm.wav", content_hash="abc", size_bytes=10)
        await session.commit()

        assert source.filename == "gm.wav"
        assert source.content_hash == "abc"
        assert source.size_bytes == 10
        assert source.transcription_state == SourceState.PENDING
        assert source.normalization_state == SourceState.PENDING

    @pytest.mark.asyncio
    async def test_registering_the_same_filename_returns_the_same_row(self, repo):
        repository, session = repo

        first = await repository.register("gm.wav", content_hash="abc")
        await session.commit()
        second = await repository.register("gm.wav", content_hash="abc")
        await session.commit()

        assert first.id == second.id
        assert len(await repository.list_sources()) == 1

    @pytest.mark.asyncio
    async def test_a_changed_hash_updates_the_row_and_keeps_its_id(self, repo):
        repository, session = repo

        first = await repository.register("gm.wav", content_hash="abc")
        await session.commit()
        second = await repository.register("gm.wav", content_hash="xyz")
        await session.commit()

        assert second.id == first.id
        assert second.content_hash == "xyz"

    @pytest.mark.asyncio
    async def test_a_changed_hash_leaves_the_previous_completion_visible_but_stale(self, repo):
        repository, session = repo

        await repository.register("gm.wav", content_hash="abc")
        await repository.mark_transcribed("gm.wav", content_hash="abc", language="en", model="base")
        await session.commit()

        assert (await repository.get_by_filename("gm.wav")).is_transcribed is True

        await repository.register("gm.wav", content_hash="different")
        await session.commit()

        source = await repository.get_by_filename("gm.wav")
        assert source.transcription_state == SourceState.DONE
        assert source.is_transcribed is False


class TestListing:
    @pytest.mark.asyncio
    async def test_lists_sources_by_filename(self, repo):
        repository, session = repo
        await repository.register("b.wav")
        await repository.register("a.wav")
        await session.commit()

        assert [s.filename for s in await repository.list_sources()] == ["a.wav", "b.wav"]

    @pytest.mark.asyncio
    async def test_get_by_filename_returns_none_when_absent(self, repo):
        repository, _ = repo

        assert await repository.get_by_filename("missing.wav") is None

    @pytest.mark.asyncio
    async def test_empty_repository_lists_nothing(self, repo):
        repository, _ = repo

        assert await repository.list_sources() == []


class TestSpeakerAssignment:
    @pytest.mark.asyncio
    async def test_assigns_a_speaker_and_reports_its_name(self, repo):
        repository, session = repo
        speaker = await SQLiteTranscriptRepository(session).get_or_create_speaker("GM")
        await repository.register("gm.wav")
        await session.commit()

        await repository.set_speaker("gm.wav", speaker.id)
        await session.commit()

        source = await repository.get_by_filename("gm.wav")
        assert source.speaker_id == speaker.id
        assert source.speaker_name == "GM"

    @pytest.mark.asyncio
    async def test_clearing_a_speaker(self, repo):
        repository, session = repo
        speaker = await SQLiteTranscriptRepository(session).get_or_create_speaker("GM")
        await repository.register("gm.wav")
        await repository.set_speaker("gm.wav", speaker.id)
        await session.commit()

        await repository.set_speaker("gm.wav", None)
        await session.commit()

        assert (await repository.get_by_filename("gm.wav")).speaker_id is None

    @pytest.mark.asyncio
    async def test_assigning_to_an_unknown_source_raises(self, repo):
        repository, _ = repo

        with pytest.raises(KeyError):
            await repository.set_speaker("nope.wav", None)


class TestTranscriptionState:
    @pytest.mark.asyncio
    async def test_marking_running_then_transcribed(self, repo):
        repository, session = repo
        await repository.register("gm.wav", content_hash="abc")
        await session.commit()

        await repository.mark_transcribing("gm.wav")
        await session.commit()
        assert (await repository.get_by_filename("gm.wav")).transcription_state == (
            SourceState.RUNNING
        )

        await repository.mark_transcribed("gm.wav", content_hash="abc", language="en", model="base")
        await session.commit()

        source = await repository.get_by_filename("gm.wav")
        assert source.transcription_state == SourceState.DONE
        assert source.is_transcribed is True
        assert source.transcription_language == "en"
        assert source.transcription_model == "base"
        assert isinstance(source.transcribed_at, datetime)
        assert source.transcription_error is None

    @pytest.mark.asyncio
    async def test_marking_failed_records_the_error(self, repo):
        repository, session = repo
        await repository.register("gm.wav", content_hash="abc")
        await session.commit()

        await repository.mark_transcription_failed("gm.wav", "model exploded")
        await session.commit()

        source = await repository.get_by_filename("gm.wav")
        assert source.transcription_state == SourceState.FAILED
        assert source.transcription_error == "model exploded"
        assert source.is_transcribed is False

    @pytest.mark.asyncio
    async def test_a_successful_run_clears_a_previous_error(self, repo):
        repository, session = repo
        await repository.register("gm.wav", content_hash="abc")
        await repository.mark_transcription_failed("gm.wav", "boom")
        await session.commit()

        await repository.mark_transcribed("gm.wav", content_hash="abc", language="en", model="base")
        await session.commit()

        assert (await repository.get_by_filename("gm.wav")).transcription_error is None


class TestNormalizationState:
    @pytest.mark.asyncio
    async def test_marking_normalized_records_the_output_and_loudness(self, repo):
        repository, session = repo
        await repository.register("gm.wav", content_hash="abc")
        await session.commit()

        await repository.mark_normalized(
            "gm.wav",
            content_hash="abc",
            normalized_filename="gm.normalized.wav",
            loudness_before=-31.2,
            loudness_after=-18.0,
        )
        await session.commit()

        source = await repository.get_by_filename("gm.wav")
        assert source.normalization_state == SourceState.DONE
        assert source.is_normalized is True
        assert source.normalized_filename == "gm.normalized.wav"
        assert source.loudness_before == -31.2
        assert source.loudness_after == -18.0

    @pytest.mark.asyncio
    async def test_normalization_failure_is_recorded(self, repo):
        repository, session = repo
        await repository.register("gm.wav", content_hash="abc")
        await session.commit()

        await repository.mark_normalization_failed("gm.wav", "no audio stream")
        await session.commit()

        source = await repository.get_by_filename("gm.wav")
        assert source.normalization_state == SourceState.FAILED
        assert source.normalization_error == "no audio stream"
        assert source.is_normalized is False

    @pytest.mark.asyncio
    async def test_transcription_and_normalization_states_are_independent(self, repo):
        repository, session = repo
        await repository.register("gm.wav", content_hash="abc")
        await repository.mark_transcribed("gm.wav", content_hash="abc", language="en", model="base")
        await session.commit()

        source = await repository.get_by_filename("gm.wav")
        assert source.is_transcribed is True
        assert source.is_normalized is False


class TestDeletion:
    @pytest.mark.asyncio
    async def test_deletes_by_filename(self, repo):
        repository, session = repo
        await repository.register("gm.wav")
        await session.commit()

        await repository.delete("gm.wav")
        await session.commit()

        assert await repository.get_by_filename("gm.wav") is None

    @pytest.mark.asyncio
    async def test_deleting_an_unknown_filename_is_a_noop(self, repo):
        repository, session = repo

        await repository.delete("nope.wav")
        await session.commit()
