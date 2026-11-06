"""Tests for SQLiteTaskRepository."""

from datetime import datetime

import pytest

from chronicler.core.models import Chronicle, Task, TaskStatus, TaskType
from chronicler.core.sqlite import (
    SQLiteChronicleRepository,
    SQLiteTaskRepository,
)


@pytest.mark.asyncio
async def test_create_and_get_task(async_session):
    repo = SQLiteTaskRepository(async_session)
    task = Task(type=TaskType.IMPORT, data='{"file": "test.mp3"}')

    created = await repo.create(task)
    assert created.id == task.id
    assert created.type == TaskType.IMPORT
    assert created.status == TaskStatus.PENDING

    fetched = await repo.get_by_id(task.id)
    assert fetched is not None
    assert fetched.id == task.id
    assert fetched.type == TaskType.IMPORT


@pytest.mark.asyncio
async def test_get_all_tasks(async_session):
    repo = SQLiteTaskRepository(async_session)
    await repo.create(Task(type=TaskType.IMPORT))
    await repo.create(Task(type=TaskType.TRANSCRIBE))

    all_tasks = await repo.get_all()
    assert len(all_tasks) == 2
    assert {t.type for t in all_tasks} == {TaskType.IMPORT, TaskType.TRANSCRIBE}


@pytest.mark.asyncio
async def test_get_all_tasks_orders_newest_first(async_session):
    repo = SQLiteTaskRepository(async_session)
    older = await repo.create(Task(type=TaskType.IMPORT, created_at=datetime(2026, 1, 1)))
    newer = await repo.create(Task(type=TaskType.TRANSCRIBE, created_at=datetime(2026, 1, 2)))

    all_tasks = await repo.get_all()

    assert [t.id for t in all_tasks] == [newer.id, older.id]


@pytest.mark.asyncio
async def test_search_tasks_orders_newest_first(async_session):
    repo = SQLiteTaskRepository(async_session)
    older = await repo.create(Task(type=TaskType.IMPORT, created_at=datetime(2026, 1, 1)))
    newer = await repo.create(Task(type=TaskType.IMPORT, created_at=datetime(2026, 1, 2)))

    results = await repo.search("IMPORT")

    assert [t.id for t in results] == [newer.id, older.id]


@pytest.mark.asyncio
async def test_update_task_status(async_session):
    repo = SQLiteTaskRepository(async_session)
    task = await repo.create(Task(type=TaskType.TRANSCRIBE))

    await repo.update_status(task.id, TaskStatus.WORKING)

    fetched = await repo.get_by_id(task.id)
    assert fetched.status == TaskStatus.WORKING

    await repo.update_status(task.id, TaskStatus.FAILED, error="Something went wrong")
    fetched = await repo.get_by_id(task.id)
    assert fetched.status == TaskStatus.FAILED
    assert fetched.error == "Something went wrong"


@pytest.mark.asyncio
async def test_returning_a_task_to_pending_clears_the_previous_runs_traces(async_session):
    """Progress, error and the claim all describe the run that just ended."""
    repo = SQLiteTaskRepository(async_session)
    task = await repo.create(Task(type=TaskType.IMPORT))
    await repo.claim_next("worker-1")
    await repo.update_progress(task.id, 60)
    await repo.update_status(task.id, TaskStatus.FAILED, error="boom")

    await repo.update_status(task.id, TaskStatus.PENDING)

    fetched = await repo.get_by_id(task.id)
    assert fetched.status == TaskStatus.PENDING
    assert fetched.error is None
    assert fetched.progress == 0
    assert fetched.claimed_by is None
    assert fetched.claimed_at is None


@pytest.mark.asyncio
async def test_a_retried_task_keeps_its_attempt_count_and_is_claimable_once(async_session):
    """
    A manually retried task is claimable again, but its spent automatic budget stays spent -
    so one retry buys one attempt, not another full round of three.
    """
    repo = SQLiteTaskRepository(async_session)
    task = await repo.create(Task(type=TaskType.IMPORT, max_attempts=1))
    await repo.claim_next("worker-1")
    await repo.mark_failed_or_retry(task.id, "boom")
    assert (await repo.get_by_id(task.id)).status == TaskStatus.FAILED

    await repo.update_status(task.id, TaskStatus.PENDING)

    assert (await repo.get_by_id(task.id)).attempts == 1
    claimed = await repo.claim_next("worker-2")
    assert claimed is not None and claimed.id == task.id

    await repo.mark_failed_or_retry(task.id, "boom again")
    assert (await repo.get_by_id(task.id)).status == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_search_tasks(async_session):
    chronicle_repo = SQLiteChronicleRepository(async_session)
    task_repo = SQLiteTaskRepository(async_session)

    chronicle = await chronicle_repo.create(Chronicle(title="D&D Session"))

    await task_repo.create(Task(type=TaskType.IMPORT, chronicle_id=chronicle.id))
    await task_repo.create(Task(type=TaskType.TRANSCRIBE))

    results = await task_repo.search("IMPORT")
    assert len(results) == 1
    assert results[0].type == TaskType.IMPORT

    results = await task_repo.search("D&D")
    assert len(results) == 1
    assert results[0].type == TaskType.IMPORT

    results = await task_repo.search("d&d")
    assert len(results) == 1


async def _working(repo, **fields) -> Task:
    task = await repo.create(Task(type=TaskType.IMPORT, **fields))
    claimed = await repo.claim_next("crashed-worker")
    assert claimed is not None and claimed.id == task.id
    await repo.update_progress(task.id, 40)
    return task


@pytest.mark.asyncio
async def test_recovery_returns_an_interrupted_task_to_the_queue(async_session):
    repo = SQLiteTaskRepository(async_session)
    task = await _working(repo)

    (recovered,) = await repo.recover_interrupted("Interrupted before finishing")

    assert recovered.id == task.id
    fetched = await repo.get_by_id(task.id)
    assert fetched is not None
    assert fetched.status == TaskStatus.PENDING
    assert fetched.claimed_by is None
    assert fetched.claimed_at is None
    assert fetched.progress == 0
    assert fetched.error == "Interrupted before finishing"
    assert fetched.attempts == 1


@pytest.mark.asyncio
async def test_recovery_fails_a_task_whose_attempts_are_used_up(async_session):
    """A task that takes the process down every time must not be retried forever."""
    repo = SQLiteTaskRepository(async_session)
    task = await _working(repo, attempts=2, max_attempts=3)

    (recovered,) = await repo.recover_interrupted("Interrupted before finishing")

    assert recovered.status == TaskStatus.FAILED
    assert recovered.attempts == 3
    assert recovered.error == "Interrupted before finishing"
    assert await repo.claim_next("worker") is None
    fetched = await repo.get_by_id(task.id)
    assert fetched is not None and fetched.status == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_recovery_leaves_tasks_that_are_not_working_alone(async_session):
    repo = SQLiteTaskRepository(async_session)
    pending = await repo.create(Task(type=TaskType.IMPORT))
    done = await repo.create(Task(type=TaskType.IMPORT, status=TaskStatus.DONE))
    failed = await repo.create(Task(type=TaskType.IMPORT, status=TaskStatus.FAILED))

    assert await repo.recover_interrupted("Interrupted before finishing") == []

    for task in (pending, done, failed):
        fetched = await repo.get_by_id(task.id)
        assert fetched is not None
        assert fetched.status == task.status
        assert fetched.attempts == 0
        assert fetched.error is None
