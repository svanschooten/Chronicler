import pytest

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import Chronicle, SourceState
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.core.sqlite import SQLiteChronicleRepository, SQLiteTranscriptRepository


async def _service(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    session = db_manager.get_archive_session()
    repo = SQLiteChronicleRepository(session)
    chronicle = await repo.create(Chronicle(title="Session"))
    await session.commit()
    return db_manager, session, TranscriptService(db_manager, repo), chronicle


def _add_track(db_manager, chronicle_id, name, content=b"audio"):
    path = db_manager.get_chronicle_sources_path(str(chronicle_id)) / name
    path.write_bytes(content)
    return path


@pytest.mark.asyncio
async def test_listing_registers_files_found_on_disk(tmp_path):
    db_manager, session, service, chronicle = await _service(tmp_path)
    try:
        _add_track(db_manager, chronicle.id, "gm.wav")
        _add_track(db_manager, chronicle.id, "player.wav")

        sources = await service.list_audio_sources(chronicle.id)

        assert [s.filename for s in sources] == ["gm.wav", "player.wav"]
        assert all(s.transcription_state == SourceState.PENDING for s in sources)
        assert all(s.content_hash for s in sources)
        assert all(s.missing is False for s in sources)
    finally:
        await session.close()
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_listing_is_idempotent(tmp_path):
    db_manager, session, service, chronicle = await _service(tmp_path)
    try:
        _add_track(db_manager, chronicle.id, "gm.wav")

        first = await service.list_audio_sources(chronicle.id)
        second = await service.list_audio_sources(chronicle.id)

        assert [s.id for s in first] == [s.id for s in second]
    finally:
        await session.close()
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_state_survives_a_relisting(tmp_path):
    db_manager, session, service, chronicle = await _service(tmp_path)
    try:
        _add_track(db_manager, chronicle.id, "gm.wav")
        await service.list_audio_sources(chronicle.id)
        await service.assign_speaker(chronicle.id, "gm.wav", "GM")

        sources = await service.list_audio_sources(chronicle.id)

        assert sources[0].speaker_name == "GM"
    finally:
        await session.close()
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_a_deleted_file_is_reported_as_missing_not_dropped(tmp_path):
    db_manager, session, service, chronicle = await _service(tmp_path)
    try:
        path = _add_track(db_manager, chronicle.id, "gm.wav")
        await service.list_audio_sources(chronicle.id)
        await service.assign_speaker(chronicle.id, "gm.wav", "GM")
        path.unlink()

        sources = await service.list_audio_sources(chronicle.id)

        assert len(sources) == 1
        assert sources[0].missing is True
        assert sources[0].speaker_name == "GM"
    finally:
        await session.close()
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_replacing_a_file_invalidates_its_completion(tmp_path):
    db_manager, session, service, chronicle = await _service(tmp_path)
    try:
        path = _add_track(db_manager, chronicle.id, "gm.wav", b"original")
        await service.list_audio_sources(chronicle.id)
        await service.mark_source_transcribed(chronicle.id, "gm.wav", "en", "base")

        assert (await service.list_audio_sources(chronicle.id))[0].is_transcribed is True

        path.write_bytes(b"a completely different recording")
        sources = await service.list_audio_sources(chronicle.id)

        assert sources[0].is_transcribed is False
        assert sources[0].transcription_state == SourceState.DONE
    finally:
        await session.close()
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_normalized_outputs_are_not_listed_as_sources(tmp_path):
    db_manager, session, service, chronicle = await _service(tmp_path)
    try:
        _add_track(db_manager, chronicle.id, "gm.wav")
        _add_track(db_manager, chronicle.id, "gm.normalized.wav")

        sources = await service.list_audio_sources(chronicle.id)

        assert [s.filename for s in sources] == ["gm.wav"]
    finally:
        await session.close()
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_assign_speaker_creates_the_speaker_row(tmp_path):
    db_manager, session, service, chronicle = await _service(tmp_path)
    try:
        _add_track(db_manager, chronicle.id, "gm.wav")
        await service.list_audio_sources(chronicle.id)

        await service.assign_speaker(chronicle.id, "gm.wav", "GM")

        project = await db_manager.get_project_session(str(chronicle.id))
        async with project:
            names = [s.name for s in await SQLiteTranscriptRepository(project).get_speakers()]
        assert names == ["GM"]
    finally:
        await session.close()
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_assigning_the_same_name_reuses_the_speaker(tmp_path):
    db_manager, session, service, chronicle = await _service(tmp_path)
    try:
        _add_track(db_manager, chronicle.id, "a.wav")
        _add_track(db_manager, chronicle.id, "b.wav")
        await service.list_audio_sources(chronicle.id)

        await service.assign_speaker(chronicle.id, "a.wav", "GM")
        await service.assign_speaker(chronicle.id, "b.wav", "GM")

        sources = await service.list_audio_sources(chronicle.id)
        assert sources[0].speaker_id == sources[1].speaker_id
    finally:
        await session.close()
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_listing_an_empty_chronicle(tmp_path):
    db_manager, session, service, chronicle = await _service(tmp_path)
    try:
        assert await service.list_audio_sources(chronicle.id) == []
    finally:
        await session.close()
        await db_manager.close_all()


async def _service_with_registry(tmp_path):
    from chronicler.core.sqlite import SQLiteKnownSpeakerRepository

    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    session = db_manager.get_archive_session()
    repo = SQLiteChronicleRepository(session)
    registry = SQLiteKnownSpeakerRepository(session)
    chronicle = await repo.create(Chronicle(title="Session"))
    await session.commit()
    return db_manager, session, TranscriptService(db_manager, repo, registry), chronicle


@pytest.mark.asyncio
async def test_assigning_a_speaker_records_it_workspace_wide(tmp_path):
    db_manager, session, service, chronicle = await _service_with_registry(tmp_path)
    try:
        _add_track(db_manager, chronicle.id, "gm.wav")
        await service.list_audio_sources(chronicle.id)

        await service.assign_speaker(chronicle.id, "gm.wav", "Alice")

        assert await service.list_known_speakers() == ["Alice"]
    finally:
        await session.close()
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_suggestions_include_speakers_from_other_chronicles(tmp_path):
    db_manager, session, service, first = await _service_with_registry(tmp_path)
    try:
        repo = SQLiteChronicleRepository(session)
        second = await repo.create(Chronicle(title="Other session"))
        await session.commit()

        _add_track(db_manager, first.id, "a.wav")
        await service.list_audio_sources(first.id)
        await service.assign_speaker(first.id, "a.wav", "Alice")

        _add_track(db_manager, second.id, "b.wav")
        await service.list_audio_sources(second.id)

        suggestions = await service.speaker_suggestions(second.id)

        assert "Alice" in suggestions
    finally:
        await session.close()
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_suggestions_merge_local_and_global_without_duplicates(tmp_path):
    db_manager, session, service, chronicle = await _service_with_registry(tmp_path)
    try:
        _add_track(db_manager, chronicle.id, "gm.wav")
        await service.list_audio_sources(chronicle.id)
        await service.assign_speaker(chronicle.id, "gm.wav", "Alice")

        suggestions = await service.speaker_suggestions(chronicle.id)

        assert suggestions.count("Alice") == 1
    finally:
        await session.close()
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_suggestions_are_empty_without_a_registry(tmp_path):
    db_manager, session, service, chronicle = await _service(tmp_path)
    try:
        assert await service.list_known_speakers() == []
        assert await service.speaker_suggestions(chronicle.id) == []
    finally:
        await session.close()
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_identifying_speakers_backfills_the_workspace_registry(tmp_path):
    """
    The manual "Identify speakers" action is the reconciliation path for chronicles that
    predate the registry, so it has to populate it rather than only counting.
    """
    from chronicler.core.sqlite import SQLiteTranscriptRepository as Transcripts

    db_manager, session, service, chronicle = await _service_with_registry(tmp_path)
    try:
        project = await db_manager.get_project_session(str(chronicle.id))
        async with project:
            repo = Transcripts(project)
            await repo.get_or_create_speaker("Alice")
            await repo.get_or_create_speaker("Bob")
            await project.commit()

        assert await service.list_known_speakers() == []

        count = await service.refresh_speaker_count(chronicle.id)

        assert count == 2
        assert await service.list_known_speakers() == ["Alice", "Bob"]
    finally:
        await session.close()
        await db_manager.close_all()
