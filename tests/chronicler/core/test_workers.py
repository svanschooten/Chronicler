import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.exc import OperationalError

from chronicler.core.database import DBChronicle
from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import Task, TaskStatus, TaskType
from chronicler.core.sqlite import SQLiteTaskRepository
from chronicler.core.task_events import TaskEventBus
from chronicler.core.workers import SessionFactory, WorkerManager


@dataclass
class Tasks:
    """The task table, each call on a fresh session so it sees what the worker wrote."""

    sessions: SessionFactory

    async def create(self, task: Task) -> Task:
        async with self.sessions() as session:
            return await SQLiteTaskRepository(session).create(task)

    async def get_by_id(self, task_id: UUID) -> Task:
        async with self.sessions() as session:
            task = await SQLiteTaskRepository(session).get_by_id(task_id)
        assert task is not None
        return task


@pytest_asyncio.fixture
async def tasks(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    yield Tasks(db_manager.get_archive_session)
    await db_manager.close_all()


@pytest.mark.asyncio
async def test_worker_manager_process_task(tasks):
    handler = AsyncMock()

    manager = WorkerManager(tasks.sessions)
    manager.register_handler(TaskType.IMPORT, handler)

    task = await tasks.create(Task(type=TaskType.IMPORT, data='{"file": "test.mp3"}'))

    await manager.process_tasks()

    handler.assert_called_once()

    fetched = await tasks.get_by_id(task.id)
    assert fetched.status == TaskStatus.DONE


@pytest.mark.asyncio
async def test_worker_manager_logs_claim_progress_and_completion(tasks, caplog):
    """
    Regression test: previously only a handler's own start-of-work log line was visible -
    nothing logged the claim, progress updates, or successful completion generically, so
    "did this task ever finish?" wasn't answerable from the logs alone.
    """

    async def handler(task, update_progress):
        await update_progress(50)

    manager = WorkerManager(tasks.sessions)
    manager.register_handler(TaskType.IMPORT, handler)
    task = await tasks.create(Task(type=TaskType.IMPORT))

    with caplog.at_level("INFO", logger="chronicler.core.workers"):
        await manager.process_tasks()

    assert f"Task {task.id}" in caplog.text
    assert "claimed, starting" in caplog.text
    assert "progress: 50%" in caplog.text
    assert "completed" in caplog.text


@pytest.mark.asyncio
async def test_worker_manager_task_failure(tasks):
    handler = AsyncMock(side_effect=Exception("Execution failed"))

    manager = WorkerManager(tasks.sessions)
    manager.register_handler(TaskType.IMPORT, handler)

    task = await tasks.create(Task(type=TaskType.IMPORT, max_attempts=1))

    await manager.process_tasks()

    fetched = await tasks.get_by_id(task.id)
    assert fetched.status == TaskStatus.FAILED
    assert "Execution failed" in fetched.error


@pytest.mark.asyncio
async def test_worker_manager_retries_before_succeeding(tasks):
    calls = 0

    async def flaky_handler(task, update_progress):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise Exception(f"attempt {calls} failed")

    manager = WorkerManager(tasks.sessions)
    manager.register_handler(TaskType.IMPORT, flaky_handler)

    task = await tasks.create(Task(type=TaskType.IMPORT))

    await manager.process_tasks()
    fetched = await tasks.get_by_id(task.id)
    assert fetched.status == TaskStatus.PENDING
    assert fetched.attempts == 1
    assert fetched.claimed_by is None

    await manager.process_tasks()
    fetched = await tasks.get_by_id(task.id)
    assert fetched.status == TaskStatus.PENDING
    assert fetched.attempts == 2

    await manager.process_tasks()
    fetched = await tasks.get_by_id(task.id)
    assert fetched.status == TaskStatus.DONE
    assert calls == 3


@pytest.mark.asyncio
async def test_worker_manager_fails_after_exhausting_max_attempts(tasks):
    handler = AsyncMock(side_effect=Exception("always fails"))

    manager = WorkerManager(tasks.sessions)
    manager.register_handler(TaskType.IMPORT, handler)

    task = await tasks.create(Task(type=TaskType.IMPORT, max_attempts=3))

    for _ in range(2):
        await manager.process_tasks()
        fetched = await tasks.get_by_id(task.id)
        assert fetched.status == TaskStatus.PENDING

    await manager.process_tasks()
    fetched = await tasks.get_by_id(task.id)
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
    assert claimed_b is None


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
async def test_completed_task_publishes_event_with_chronicle_id(tasks):
    event_bus = TaskEventBus()
    received = []
    event_bus.subscribe(lambda event: received.append(event))

    manager = WorkerManager(tasks.sessions, event_bus=event_bus)
    manager.register_handler(TaskType.IMPORT, AsyncMock())

    chronicle_id = uuid4()
    task = await tasks.create(Task(type=TaskType.IMPORT, chronicle_id=chronicle_id))

    await manager.process_tasks()

    assert len(received) == 1
    assert received[0].task_id == task.id
    assert received[0].status == TaskStatus.DONE
    assert received[0].chronicle_id == chronicle_id


@pytest.mark.asyncio
async def test_failed_task_with_no_retries_left_publishes_event(tasks):
    event_bus = TaskEventBus()
    received = []
    event_bus.subscribe(lambda event: received.append(event))

    manager = WorkerManager(tasks.sessions, event_bus=event_bus)
    manager.register_handler(TaskType.IMPORT, AsyncMock(side_effect=Exception("boom")))

    await tasks.create(Task(type=TaskType.IMPORT, max_attempts=1))
    await manager.process_tasks()

    assert len(received) == 1
    assert received[0].status == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_task_retry_does_not_publish_event_yet(tasks):
    """
    A task that still has retries left goes back to PENDING, not a terminal state - nothing
    has "completed" from a listener's point of view yet.
    """
    event_bus = TaskEventBus()
    received = []
    event_bus.subscribe(lambda event: received.append(event))

    manager = WorkerManager(tasks.sessions, event_bus=event_bus)
    manager.register_handler(TaskType.IMPORT, AsyncMock(side_effect=Exception("boom")))

    await tasks.create(Task(type=TaskType.IMPORT, max_attempts=3))
    await manager.process_tasks()

    assert received == []


@pytest.mark.asyncio
async def test_no_event_bus_configured_does_not_raise(tasks):
    manager = WorkerManager(tasks.sessions)
    manager.register_handler(TaskType.IMPORT, AsyncMock())

    await tasks.create(Task(type=TaskType.IMPORT))
    await manager.process_tasks()


async def _progress_reporting_handler(task, update_progress):
    """A stand-in for a real handler: sleeps, reports progress, sleeps, finishes."""
    await asyncio.sleep(1)
    await update_progress(50)
    await asyncio.sleep(1)
    await update_progress(100)


@pytest.mark.asyncio
async def test_test_worker_execution(tasks):
    manager = WorkerManager(tasks.sessions)
    manager.register_handler(TaskType.CLEAN, _progress_reporting_handler)

    task = await tasks.create(Task(type=TaskType.CLEAN))

    with patch("asyncio.sleep", return_value=None):
        await manager.process_tasks()

    fetched = await tasks.get_by_id(task.id)
    assert fetched.status == TaskStatus.DONE
    assert fetched.progress == 100


@pytest.mark.asyncio
async def test_task_failure_recording(tasks):
    manager = WorkerManager(tasks.sessions)

    async def failing_handler(task, update_progress):
        raise ValueError("Specific error")

    manager.register_handler(TaskType.CLEAN, failing_handler)
    task = await tasks.create(Task(type=TaskType.CLEAN, max_attempts=1))

    await manager.process_tasks()

    fetched = await tasks.get_by_id(task.id)
    assert fetched.status == TaskStatus.FAILED
    assert "Specific error" in fetched.error


@pytest.mark.asyncio
async def test_task_retry_logic(async_session):
    repo = SQLiteTaskRepository(async_session)

    task = await repo.create(
        Task(type=TaskType.CLEAN, status=TaskStatus.FAILED, error="Previous error", progress=50)
    )

    await repo.update_status(task.id, TaskStatus.PENDING)

    fetched = await repo.get_by_id(task.id)
    assert fetched.status == TaskStatus.PENDING
    assert fetched.error is None
    assert fetched.progress == 0


async def _hold_the_write_lock(session) -> None:
    """A flushed, uncommitted write: every other writer waits, then fails."""
    session.add(DBChronicle(title="holds the lock"))
    await session.flush()


@pytest.mark.asyncio
async def test_a_lock_released_during_the_status_write_still_finishes_the_task(two_sessions):
    tasks = Tasks(two_sessions.db_manager.get_archive_session)
    blocker = two_sessions.first
    manager = WorkerManager(tasks.sessions, status_write_timeout=5.0)
    release: asyncio.Task | None = None

    async def release_later():
        await asyncio.sleep(0.5)
        await blocker.rollback()

    async def handler(task, update_progress):
        nonlocal release
        await _hold_the_write_lock(blocker)
        release = asyncio.create_task(release_later())

    manager.register_handler(TaskType.IMPORT, handler)
    task = await tasks.create(Task(type=TaskType.IMPORT))

    await manager.process_tasks()
    assert release is not None and release.done()

    assert (await tasks.get_by_id(task.id)).status == TaskStatus.DONE


@pytest.mark.asyncio
async def test_a_lock_timeout_does_not_stop_later_tasks(two_sessions, caplog):
    tasks = Tasks(two_sessions.db_manager.get_archive_session)
    blocker = two_sessions.first
    manager = WorkerManager(tasks.sessions, status_write_timeout=0.3)
    ran = []

    async def handler(task, update_progress):
        ran.append(task.id)
        if len(ran) == 1:
            await _hold_the_write_lock(blocker)
        await update_progress(50)

    manager.register_handler(TaskType.IMPORT, handler)
    stuck = await tasks.create(Task(type=TaskType.IMPORT))

    with pytest.raises(OperationalError, match="database is locked"):
        await manager.process_tasks()
    await blocker.rollback()

    later = await tasks.create(Task(type=TaskType.IMPORT))
    await manager.process_tasks()

    assert ran == [stuck.id, later.id]
    assert (await tasks.get_by_id(later.id)).status == TaskStatus.DONE
    assert "PendingRollbackError" not in caplog.text


@pytest.mark.asyncio
async def test_progress_is_best_effort_while_the_database_is_locked(two_sessions):
    tasks = Tasks(two_sessions.db_manager.get_archive_session)
    blocker = two_sessions.first
    manager = WorkerManager(tasks.sessions)
    reached_the_end = False

    async def handler(task, update_progress):
        nonlocal reached_the_end
        await _hold_the_write_lock(blocker)
        await update_progress(50)
        reached_the_end = True
        await blocker.rollback()

    manager.register_handler(TaskType.IMPORT, handler)
    task = await tasks.create(Task(type=TaskType.IMPORT))

    await manager.process_tasks()

    assert reached_the_end
    assert (await tasks.get_by_id(task.id)).status == TaskStatus.DONE
