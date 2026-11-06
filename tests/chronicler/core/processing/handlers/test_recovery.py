"""
Tests for the cleanup that runs when recovery fails a TRANSCRIBE or NORMALIZE task.

A crash skips the handler's own failure path, so a source it marked RUNNING stays that way
unless this clears it. See docs/tasks.md.
"""

import json
from uuid import uuid4

import pytest
import pytest_asyncio

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import SourceState, Task, TaskStatus, TaskType
from chronicler.core.processing.handlers import WorkerHandlers
from chronicler.core.sqlite import SQLiteAudioSourceRepository, SQLiteTaskRepository
from chronicler.core.worker_wiring import build_worker_manager


@pytest.fixture(autouse=True)
def _defaults_not_the_developers_config(isolated_config):
    """`Settings()` here has to mean the shipped defaults. See docs/testing.md."""


@pytest_asyncio.fixture
async def workspace(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    yield db_manager
    await db_manager.close_all()


async def _source(db_manager, chronicle_id, filename="track.wav", **states):
    audio = db_manager.get_chronicle_sources_path(str(chronicle_id)) / filename
    audio.write_bytes(b"audio")
    session = await db_manager.get_project_session(str(chronicle_id))
    async with session:
        repo = SQLiteAudioSourceRepository(session)
        await repo.register(filename)
        if states.get("transcription") == SourceState.RUNNING:
            await repo.mark_transcribing(filename)
        if states.get("transcription") == SourceState.DONE:
            await repo.mark_transcribed(filename, None, None, None)
        if states.get("normalization") == SourceState.RUNNING:
            await repo.mark_normalizing(filename)
        await session.commit()
    return audio


async def _record(db_manager, chronicle_id, filename="track.wav"):
    session = await db_manager.get_project_session(str(chronicle_id))
    async with session:
        record = await SQLiteAudioSourceRepository(session).get_by_filename(filename)
    assert record is not None
    return record


def _task(task_type, chronicle_id, audio, **fields):
    return Task(
        type=task_type,
        chronicle_id=chronicle_id,
        data=json.dumps({"file_path": str(audio), "speaker_name": "Alice"}),
        status=TaskStatus.FAILED,
        error="Interrupted before finishing",
        **fields,
    )


@pytest.mark.asyncio
async def test_a_failed_transcribe_stops_showing_as_transcribing(workspace):
    chronicle_id = uuid4()
    audio = await _source(
        workspace,
        chronicle_id,
        transcription=SourceState.RUNNING,
        normalization=SourceState.RUNNING,
    )

    await WorkerHandlers(workspace).abandon_transcribe(
        _task(TaskType.TRANSCRIBE, chronicle_id, audio)
    )

    record = await _record(workspace, chronicle_id)
    assert record.transcription_state == SourceState.FAILED
    assert record.transcription_error == "Interrupted before finishing"
    assert record.normalization_state == SourceState.FAILED, "normalize_first runs inside it"


@pytest.mark.asyncio
async def test_a_failed_normalize_leaves_the_transcription_state_alone(workspace):
    chronicle_id = uuid4()
    audio = await _source(
        workspace,
        chronicle_id,
        transcription=SourceState.RUNNING,
        normalization=SourceState.RUNNING,
    )

    await WorkerHandlers(workspace).abandon_normalize(
        _task(TaskType.NORMALIZE, chronicle_id, audio)
    )

    record = await _record(workspace, chronicle_id)
    assert record.normalization_state == SourceState.FAILED
    assert record.transcription_state == SourceState.RUNNING


@pytest.mark.asyncio
async def test_a_source_that_got_past_running_is_left_alone(workspace):
    """The crash came after the transcript was saved, so the source really is done."""
    chronicle_id = uuid4()
    audio = await _source(workspace, chronicle_id, transcription=SourceState.DONE)

    await WorkerHandlers(workspace).abandon_transcribe(
        _task(TaskType.TRANSCRIBE, chronicle_id, audio)
    )

    assert (await _record(workspace, chronicle_id)).transcription_state == SourceState.DONE


@pytest.mark.asyncio
async def test_a_source_that_was_never_registered_is_not_created(workspace):
    chronicle_id = uuid4()
    audio = workspace.get_chronicle_sources_path(str(chronicle_id)) / "unseen.wav"

    await WorkerHandlers(workspace).abandon_transcribe(
        _task(TaskType.TRANSCRIBE, chronicle_id, audio)
    )

    session = await workspace.get_project_session(str(chronicle_id))
    async with session:
        assert await SQLiteAudioSourceRepository(session).list_sources() == []


@pytest.mark.asyncio
async def test_the_wired_worker_clears_the_source_of_a_task_recovery_fails(workspace):
    """End to end: a transcribe that crashed on its last attempt, then a restart."""
    chronicle_id = uuid4()
    audio = await _source(workspace, chronicle_id, transcription=SourceState.RUNNING)
    async with workspace.get_archive_session() as session:
        tasks = SQLiteTaskRepository(session)
        task = Task(
            type=TaskType.TRANSCRIBE,
            chronicle_id=chronicle_id,
            data=json.dumps({"file_path": str(audio), "speaker_name": "Alice"}),
            attempts=2,
            max_attempts=3,
        )
        await tasks.create(task)
        assert await tasks.claim_next("crashed-worker") is not None

    await build_worker_manager(workspace).recover_interrupted()

    record = await _record(workspace, chronicle_id)
    assert record.transcription_state == SourceState.FAILED
    assert record.transcription_error == "Interrupted before finishing"
