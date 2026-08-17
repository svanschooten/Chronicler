import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from chronicler.core.models import Task, TaskStatus, TaskType
from chronicler.core.sqlite import SQLiteTaskRepository
from chronicler.core.task_events import TaskEventBus
from chronicler.core.workers import WorkerManager


@pytest.mark.asyncio
async def test_worker_manager_process_task(async_session):
    repo = SQLiteTaskRepository(async_session)
    handler = AsyncMock()

    manager = WorkerManager(repo)
    manager.register_handler(TaskType.IMPORT, handler)

    task = await repo.create(Task(type=TaskType.IMPORT, data='{"file": "test.mp3"}'))

    await manager.process_tasks()

    handler.assert_called_once()

    fetched = await repo.get_by_id(task.id)
    assert fetched.status == TaskStatus.DONE


@pytest.mark.asyncio
async def test_worker_manager_logs_claim_progress_and_completion(async_session, caplog):
    """Regression test: previously only a handler's own start-of-work log line was
    visible - nothing logged the claim, progress updates, or successful completion
    generically, so "did this task ever finish?" wasn't answerable from the logs
    alone.
    """
    repo = SQLiteTaskRepository(async_session)

    async def handler(task, update_progress):
        await update_progress(50)

    manager = WorkerManager(repo)
    manager.register_handler(TaskType.IMPORT, handler)
    task = await repo.create(Task(type=TaskType.IMPORT))

    with caplog.at_level("INFO", logger="chronicler.core.workers"):
        await manager.process_tasks()

    assert f"Task {task.id}" in caplog.text
    assert "claimed, starting" in caplog.text
    assert "progress: 50%" in caplog.text
    assert "completed" in caplog.text


@pytest.mark.asyncio
async def test_worker_manager_task_failure(async_session):
    repo = SQLiteTaskRepository(async_session)
    handler = AsyncMock(side_effect=Exception("Execution failed"))

    manager = WorkerManager(repo)
    manager.register_handler(TaskType.IMPORT, handler)

    # max_attempts=1: this test is about failure recording, not retry - see the
    # dedicated retry tests below for that.
    task = await repo.create(Task(type=TaskType.IMPORT, max_attempts=1))

    await manager.process_tasks()

    fetched = await repo.get_by_id(task.id)
    assert fetched.status == TaskStatus.FAILED
    assert "Execution failed" in fetched.error


@pytest.mark.asyncio
async def test_worker_manager_retries_before_succeeding(async_session):
    repo = SQLiteTaskRepository(async_session)
    calls = 0

    async def flaky_handler(task, update_progress):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise Exception(f"attempt {calls} failed")

    manager = WorkerManager(repo)
    manager.register_handler(TaskType.IMPORT, flaky_handler)

    task = await repo.create(Task(type=TaskType.IMPORT))

    # Each process_tasks() call claims and runs whatever is currently PENDING; a
    # retried task only becomes PENDING again after mark_failed_or_retry, so it takes
    # one process_tasks() call per attempt.
    await manager.process_tasks()
    fetched = await repo.get_by_id(task.id)
    assert fetched.status == TaskStatus.PENDING
    assert fetched.attempts == 1
    assert fetched.claimed_by is None  # cleared on retry, eligible to be reclaimed

    await manager.process_tasks()
    fetched = await repo.get_by_id(task.id)
    assert fetched.status == TaskStatus.PENDING
    assert fetched.attempts == 2

    await manager.process_tasks()
    fetched = await repo.get_by_id(task.id)
    assert fetched.status == TaskStatus.DONE
    assert calls == 3


@pytest.mark.asyncio
async def test_worker_manager_fails_after_exhausting_max_attempts(async_session):
    repo = SQLiteTaskRepository(async_session)
    handler = AsyncMock(side_effect=Exception("always fails"))

    manager = WorkerManager(repo)
    manager.register_handler(TaskType.IMPORT, handler)

    task = await repo.create(Task(type=TaskType.IMPORT, max_attempts=3))

    for _ in range(2):
        await manager.process_tasks()
        fetched = await repo.get_by_id(task.id)
        assert fetched.status == TaskStatus.PENDING

    await manager.process_tasks()
    fetched = await repo.get_by_id(task.id)
    assert fetched.status == TaskStatus.FAILED
    assert fetched.attempts == 3
    assert "always fails" in fetched.error


@pytest.mark.asyncio
async def test_claim_next_is_atomic_under_contention(async_session):
    """Two 'workers' racing for the same pending task must never both claim it."""
    repo = SQLiteTaskRepository(async_session)
    task = await repo.create(Task(type=TaskType.IMPORT))

    claimed_a = await repo.claim_next("worker-a")
    claimed_b = await repo.claim_next("worker-b")

    assert claimed_a is not None
    assert claimed_a.id == task.id
    assert claimed_a.claimed_by == "worker-a"
    assert claimed_b is None  # nothing left to claim


@pytest.mark.asyncio
async def test_claim_next_skips_tasks_already_claimed(async_session):
    repo = SQLiteTaskRepository(async_session)
    await repo.create(Task(type=TaskType.IMPORT, priority=1))
    second = await repo.create(Task(type=TaskType.IMPORT, priority=0))

    first_claim = await repo.claim_next("worker-a")
    assert first_claim is not None

    second_claim = await repo.claim_next("worker-b")
    assert second_claim is not None
    assert second_claim.id == second.id
    assert second_claim.claimed_by == "worker-b"

    assert await repo.claim_next("worker-c") is None


@pytest.mark.asyncio
async def test_completed_task_publishes_event_with_chronicle_id(async_session):
    repo = SQLiteTaskRepository(async_session)
    event_bus = TaskEventBus()
    received = []
    event_bus.subscribe(lambda event: received.append(event))

    manager = WorkerManager(repo, event_bus=event_bus)
    manager.register_handler(TaskType.IMPORT, AsyncMock())

    chronicle_id = uuid4()
    task = await repo.create(Task(type=TaskType.IMPORT, chronicle_id=chronicle_id))

    await manager.process_tasks()

    assert len(received) == 1
    assert received[0].task_id == task.id
    assert received[0].status == TaskStatus.DONE
    assert received[0].chronicle_id == chronicle_id


@pytest.mark.asyncio
async def test_failed_task_with_no_retries_left_publishes_event(async_session):
    repo = SQLiteTaskRepository(async_session)
    event_bus = TaskEventBus()
    received = []
    event_bus.subscribe(lambda event: received.append(event))

    manager = WorkerManager(repo, event_bus=event_bus)
    manager.register_handler(TaskType.IMPORT, AsyncMock(side_effect=Exception("boom")))

    await repo.create(Task(type=TaskType.IMPORT, max_attempts=1))
    await manager.process_tasks()

    assert len(received) == 1
    assert received[0].status == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_task_retry_does_not_publish_event_yet(async_session):
    """A task that still has retries left goes back to PENDING, not a terminal
    state - nothing has "completed" from a listener's point of view yet."""
    repo = SQLiteTaskRepository(async_session)
    event_bus = TaskEventBus()
    received = []
    event_bus.subscribe(lambda event: received.append(event))

    manager = WorkerManager(repo, event_bus=event_bus)
    manager.register_handler(TaskType.IMPORT, AsyncMock(side_effect=Exception("boom")))

    await repo.create(Task(type=TaskType.IMPORT, max_attempts=3))
    await manager.process_tasks()

    assert received == []


@pytest.mark.asyncio
async def test_no_event_bus_configured_does_not_raise(async_session):
    repo = SQLiteTaskRepository(async_session)
    manager = WorkerManager(repo)  # no event_bus
    manager.register_handler(TaskType.IMPORT, AsyncMock())

    await repo.create(Task(type=TaskType.IMPORT))
    await manager.process_tasks()  # must not raise


async def _progress_reporting_handler(task, update_progress):
    """A stand-in for a real handler: sleeps, reports progress, sleeps, finishes. The
    sleeps are what tests patch out - they exist so this exercises the same
    await-in-the-middle shape a real handler has."""
    await asyncio.sleep(1)
    await update_progress(50)
    await asyncio.sleep(1)
    await update_progress(100)


@pytest.mark.asyncio
async def test_test_worker_execution(async_session):
    repo = SQLiteTaskRepository(async_session)
    manager = WorkerManager(repo)
    manager.register_handler(TaskType.TEST, _progress_reporting_handler)

    task = await repo.create(Task(type=TaskType.TEST))

    # Mock asyncio.sleep to speed up test
    with patch("asyncio.sleep", return_value=None):
        await manager.process_tasks()

    fetched = await repo.get_by_id(task.id)
    assert fetched.status == TaskStatus.DONE
    assert fetched.progress == 100


@pytest.mark.asyncio
async def test_task_failure_recording(async_session):
    repo = SQLiteTaskRepository(async_session)
    manager = WorkerManager(repo)

    async def failing_handler(task, update_progress):
        raise ValueError("Specific error")

    manager.register_handler(TaskType.TEST, failing_handler)
    # max_attempts=1: this test is about failure recording, not retry - the
    # retry-specific tests are above.
    task = await repo.create(Task(type=TaskType.TEST, max_attempts=1))

    await manager.process_tasks()

    fetched = await repo.get_by_id(task.id)
    assert fetched.status == TaskStatus.FAILED
    assert "Specific error" in fetched.error


@pytest.mark.asyncio
async def test_task_retry_logic(async_session):
    repo = SQLiteTaskRepository(async_session)

    # Create a failed task with error and progress
    task = await repo.create(
        Task(type=TaskType.TEST, status=TaskStatus.FAILED, error="Previous error", progress=50)
    )

    # Retry the task
    await repo.update_status(task.id, TaskStatus.PENDING)

    fetched = await repo.get_by_id(task.id)
    assert fetched.status == TaskStatus.PENDING
    assert fetched.error is None
    assert fetched.progress == 0
