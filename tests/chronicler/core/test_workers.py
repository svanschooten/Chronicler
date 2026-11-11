import asyncio
import sqlite3
from contextlib import contextmanager
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


@pytest.fixture
def no_backoff(monkeypatch):
    """Retries are due at once, so a test can drive several attempts back to back."""
    monkeypatch.setattr(SQLiteTaskRepository, "retry_delays", (0.0,))


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
async def test_a_failed_task_is_not_retried_until_its_delay_has_passed(tasks):
    calls = 0

    async def always_fails(task, update_progress):
        nonlocal calls
        calls += 1
        raise Exception("down")

    manager = WorkerManager(tasks.sessions)
    manager.register_handler(TaskType.IMPORT, always_fails)
    task = await tasks.create(Task(type=TaskType.IMPORT))

    await manager.process_tasks()
    await manager.process_tasks()

    fetched = await tasks.get_by_id(task.id)
    assert calls == 1
    assert fetched.status == TaskStatus.PENDING
    assert fetched.not_before is not None


@pytest.mark.asyncio
async def test_worker_manager_retries_before_succeeding(tasks, no_backoff):
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
    assert fetched.status == TaskStatus.DONE
    assert calls == 3


@pytest.mark.asyncio
async def test_worker_manager_fails_after_exhausting_max_attempts(tasks, no_backoff):
    handler = AsyncMock(side_effect=Exception("always fails"))

    manager = WorkerManager(tasks.sessions)
    manager.register_handler(TaskType.IMPORT, handler)
    task = await tasks.create(Task(type=TaskType.IMPORT, max_attempts=3))

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


async def _interrupted(tasks: Tasks, **fields) -> Task:
    """A task a crashed worker claimed and never finished."""
    task = await tasks.create(Task(type=TaskType.IMPORT, **fields))
    async with tasks.sessions() as session:
        assert await SQLiteTaskRepository(session).claim_next("crashed-worker") is not None
    return task


async def _run_until(manager: WorkerManager, done: asyncio.Event) -> None:
    runner = asyncio.create_task(manager.run_forever(interval=0.01))
    try:
        await asyncio.wait_for(done.wait(), timeout=5)
    finally:
        manager.stop()
        await asyncio.wait_for(runner, timeout=5)


@pytest.mark.asyncio
async def test_a_task_interrupted_by_a_crash_runs_again_on_the_next_start(tasks):
    task = await _interrupted(tasks)
    ran = asyncio.Event()

    async def handler(_task, _progress):
        ran.set()

    manager = WorkerManager(tasks.sessions)
    manager.register_handler(TaskType.IMPORT, handler)
    await _run_until(manager, ran)

    fetched = await tasks.get_by_id(task.id)
    assert fetched.status == TaskStatus.DONE
    assert fetched.attempts == 1, "the interrupted run counts as an attempt"


@pytest.mark.asyncio
async def test_recovery_fails_an_interrupted_task_with_no_attempts_left(tasks):
    task = await _interrupted(tasks, attempts=2, max_attempts=3)
    cleanup = AsyncMock()
    bus = TaskEventBus()
    events = []
    bus.subscribe(lambda event: events.append(event))

    manager = WorkerManager(tasks.sessions, event_bus=bus)
    handler = AsyncMock()
    manager.register_handler(TaskType.IMPORT, handler)
    manager.register_cleanup(TaskType.IMPORT, cleanup)
    await manager.recover_interrupted()
    await manager.process_tasks()

    fetched = await tasks.get_by_id(task.id)
    assert fetched.status == TaskStatus.FAILED
    assert fetched.error == "Interrupted before finishing"
    handler.assert_not_called()
    cleanup.assert_awaited_once()
    assert cleanup.await_args.args[0].id == task.id
    assert [(event.task_id, event.status) for event in events] == [(task.id, TaskStatus.FAILED)]


@pytest.mark.asyncio
async def test_cleanup_only_runs_for_a_task_recovery_failed(tasks):
    await _interrupted(tasks)
    cleanup = AsyncMock()

    manager = WorkerManager(tasks.sessions)
    manager.register_cleanup(TaskType.IMPORT, cleanup)
    await manager.recover_interrupted()

    cleanup.assert_not_called()


@pytest.mark.asyncio
async def test_a_failing_cleanup_does_not_stop_recovery(tasks, caplog):
    first = await _interrupted(tasks, attempts=2, max_attempts=3)
    second = await _interrupted(tasks, attempts=2, max_attempts=3)
    cleanup = AsyncMock(side_effect=RuntimeError("project database is gone"))

    manager = WorkerManager(tasks.sessions)
    manager.register_cleanup(TaskType.IMPORT, cleanup)
    await manager.recover_interrupted()

    assert cleanup.await_count == 2
    for task in (first, second):
        assert (await tasks.get_by_id(task.id)).status == TaskStatus.FAILED
    assert "Cleaning up after interrupted task" in caplog.text


@pytest.mark.asyncio
async def test_nothing_is_claimed_until_recovery_has_worked(tasks):
    """
    A task claimed before recovery ran would look interrupted to it, and be reset while
    it was running.
    """
    await tasks.create(Task(type=TaskType.IMPORT))
    ran = asyncio.Event()

    async def handler(_task, _progress):
        ran.set()

    manager = WorkerManager(tasks.sessions)
    manager.register_handler(TaskType.IMPORT, handler)
    real_recover = manager.recover_interrupted
    calls = 0

    async def flaky_recover():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OperationalError("UPDATE", {}, Exception("database is locked"))
        assert not ran.is_set()
        await real_recover()

    with patch.object(manager, "recover_interrupted", flaky_recover):
        await _run_until(manager, ran)

    assert calls == 2


@pytest.mark.asyncio
async def test_recovery_runs_once_per_start(tasks):
    manager = WorkerManager(tasks.sessions)
    recover = AsyncMock()
    cycles = 0
    enough = asyncio.Event()

    async def count_cycles():
        nonlocal cycles
        cycles += 1
        if cycles == 3:
            enough.set()

    with (
        patch.object(manager, "recover_interrupted", recover),
        patch.object(manager, "process_tasks", count_cycles),
    ):
        await _run_until(manager, enough)

    recover.assert_awaited_once()


@pytest.mark.asyncio
async def test_stopping_the_worker_mid_task_leaves_the_task_pending(tasks):
    """What closing the app during a transcription does."""
    task = await tasks.create(Task(type=TaskType.IMPORT))
    started = asyncio.Event()

    async def handler(_task, _progress):
        started.set()
        await asyncio.Event().wait()

    manager = WorkerManager(tasks.sessions)
    manager.register_handler(TaskType.IMPORT, handler)
    runner = asyncio.create_task(manager.run_forever(interval=0.01))
    await asyncio.wait_for(started.wait(), timeout=5)
    manager.stop()
    runner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await runner

    fetched = await tasks.get_by_id(task.id)
    assert fetched.status == TaskStatus.PENDING
    assert fetched.attempts == 0, "being stopped is not the task's failure"
    assert fetched.claimed_by is None
    assert fetched.error is None


@pytest.mark.asyncio
async def test_a_stop_that_cannot_requeue_leaves_the_task_to_recovery(two_sessions, caplog):
    """Shutdown must not wait on a locked database; the next start's recovery covers it."""
    sessions = two_sessions.db_manager.get_archive_session
    tasks = Tasks(sessions)
    task = await tasks.create(Task(type=TaskType.IMPORT))
    started = asyncio.Event()

    async def handler(_task, _progress):
        started.set()
        await asyncio.Event().wait()

    manager = WorkerManager(sessions)
    manager.register_handler(TaskType.IMPORT, handler)
    runner = asyncio.create_task(manager.run_forever(interval=0.01))
    await asyncio.wait_for(started.wait(), timeout=5)
    await _hold_the_write_lock(two_sessions.first)
    runner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await runner
    await two_sessions.first.rollback()

    assert (await tasks.get_by_id(task.id)).status == TaskStatus.WORKING
    assert "could not return it to the queue" in caplog.text

    await WorkerManager(sessions).recover_interrupted()
    assert (await tasks.get_by_id(task.id)).status == TaskStatus.PENDING


@pytest.mark.asyncio
async def test_stopping_while_the_outcome_waits_on_a_lock_still_records_it(two_sessions, caplog):
    """The work is finished; being stopped then must not make the next start redo it."""
    sessions = two_sessions.db_manager.get_archive_session
    tasks = Tasks(sessions)
    blocker = two_sessions.first
    task = await tasks.create(Task(type=TaskType.IMPORT))

    async def handler(_task, _progress):
        await _hold_the_write_lock(blocker)

    manager = WorkerManager(sessions, status_write_timeout=30.0)
    manager.register_handler(TaskType.IMPORT, handler)
    runner = asyncio.create_task(manager.run_forever(interval=0.01))

    async def retrying_for_a_while():
        # The second retry sleeps 0.2 s, long enough for the stop to land inside it.
        while caplog.text.count("retrying a task status write") < 2:
            await asyncio.sleep(0.01)

    await asyncio.wait_for(retrying_for_a_while(), timeout=10)
    await blocker.rollback()
    runner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await runner

    fetched = await tasks.get_by_id(task.id)
    assert fetched.status == TaskStatus.DONE
    assert fetched.attempts == 0


@pytest.mark.asyncio
async def test_a_stop_whose_last_try_is_locked_leaves_the_task_to_recovery(two_sessions, caplog):
    sessions = two_sessions.db_manager.get_archive_session
    tasks = Tasks(sessions)
    blocker = two_sessions.first
    task = await tasks.create(Task(type=TaskType.IMPORT))

    async def handler(_task, _progress):
        await _hold_the_write_lock(blocker)

    manager = WorkerManager(sessions, status_write_timeout=30.0)
    manager.register_handler(TaskType.IMPORT, handler)
    runner = asyncio.create_task(manager.run_forever(interval=0.01))

    async def retrying():
        while "retrying a task status write" not in caplog.text:
            await asyncio.sleep(0.01)

    await asyncio.wait_for(retrying(), timeout=10)
    runner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await runner
    await blocker.rollback()

    assert (await tasks.get_by_id(task.id)).status == TaskStatus.WORKING
    assert "it will run again after the next start" in caplog.text


@pytest.mark.asyncio
async def test_a_failed_announcement_does_not_skip_the_next_tasks_cleanup(tasks, caplog):
    """The rows are already committed, so a retry would never get back to these."""
    first = await _interrupted(tasks, attempts=2, max_attempts=3)
    second = await _interrupted(tasks, attempts=2, max_attempts=3)
    cleanup = AsyncMock()

    manager = WorkerManager(tasks.sessions, event_bus=TaskEventBus())
    manager.register_cleanup(TaskType.IMPORT, cleanup)
    real_publish = manager._publish_completion
    announced = []

    async def flaky_publish(task_id):
        if not announced:
            announced.append(None)
            raise OperationalError("SELECT", {}, Exception("database is locked"))
        await real_publish(task_id)

    with patch.object(manager, "_publish_completion", flaky_publish):
        await manager.recover_interrupted()

    assert {call.args[0].id for call in cleanup.await_args_list} == {first.id, second.id}
    assert "Could not announce that interrupted task" in caplog.text


@contextmanager
def _exclusive_lock(db_path):
    """
    Holds an EXCLUSIVE lock on the real database file from another connection, which
    blocks readers too: a flushed write only blocks other writers, and `_publish_completion`
    only reads.
    """
    connection = sqlite3.connect(db_path, isolation_level=None)
    connection.execute("BEGIN EXCLUSIVE")
    try:
        yield connection
    finally:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        connection.close()


def _lock_during_publish(manager: WorkerManager, db_path, release_after: float | None):
    """
    Wraps `_publish_completion` so the database is locked exactly while it runs: the
    status write before it has already gone through. Released after `release_after`
    seconds, or only when the publish is over.
    """
    original = manager._publish_completion

    async def locked(task_id):
        with _exclusive_lock(db_path) as connection:
            if release_after is not None:
                asyncio.get_running_loop().call_later(
                    release_after, lambda: connection.execute("ROLLBACK")
                )
            await original(task_id)

    return locked


@pytest.mark.asyncio
async def test_the_completion_event_survives_a_busy_database(two_sessions, caplog):
    tasks = Tasks(two_sessions.db_manager.get_archive_session)
    bus = TaskEventBus()
    received = []
    bus.subscribe(received.append)
    manager = WorkerManager(tasks.sessions, event_bus=bus, status_write_timeout=5.0)
    manager.register_handler(TaskType.IMPORT, AsyncMock())
    db_path = two_sessions.db_manager.archive_db_path
    # Well past the fixture's 0.2s busy timeout, so the first read fails and a retry is
    # what succeeds.
    manager._publish_completion = _lock_during_publish(manager, db_path, release_after=1.0)
    await tasks.create(Task(type=TaskType.IMPORT))

    await manager.process_tasks()

    assert [event.status for event in received] == [TaskStatus.DONE]
    assert "retrying reading a finished task" in caplog.text


@pytest.mark.asyncio
async def test_a_busy_database_that_never_clears_does_not_fail_the_worker(two_sessions, caplog):
    tasks = Tasks(two_sessions.db_manager.get_archive_session)
    bus = TaskEventBus()
    received = []
    bus.subscribe(received.append)
    manager = WorkerManager(tasks.sessions, event_bus=bus, status_write_timeout=0.5)
    manager.register_handler(TaskType.IMPORT, AsyncMock())
    db_path = two_sessions.db_manager.archive_db_path
    manager._publish_completion = _lock_during_publish(manager, db_path, release_after=None)
    task = await tasks.create(Task(type=TaskType.IMPORT))

    await manager.process_tasks()

    assert received == []
    assert "could not read it back" in caplog.text
    assert (await tasks.get_by_id(task.id)).status == TaskStatus.DONE


@pytest.mark.asyncio
async def test_an_error_that_is_not_a_lock_is_not_retried(tasks, caplog):
    manager = WorkerManager(tasks.sessions, event_bus=TaskEventBus(), status_write_timeout=5.0)
    calls = 0

    async def broken(_tasks):
        nonlocal calls
        calls += 1
        raise OperationalError("SELECT", {}, Exception("no such table: tasks"))

    with pytest.raises(OperationalError, match="no such table"):
        await manager._retry_while_busy(broken, "a broken read")

    assert calls == 1
    assert "retrying" not in caplog.text


@pytest.mark.asyncio
async def test_a_task_cancelled_while_running_is_stopped_and_not_retried(tasks, monkeypatch):
    monkeypatch.setattr("chronicler.core.workers.CANCEL_POLL_SECONDS", 0.01)
    manager = WorkerManager(tasks.sessions)
    started = asyncio.Event()

    async def handler(task, update_progress):
        from chronicler.core.cancellation import raise_if_cancelled

        started.set()
        while True:
            await asyncio.sleep(0.01)
            raise_if_cancelled()

    manager.register_handler(TaskType.TRANSCRIBE, handler)
    task = await tasks.create(Task(type=TaskType.TRANSCRIBE))

    async def cancel_once_running():
        await started.wait()
        async with tasks.sessions() as session:
            assert await SQLiteTaskRepository(session).cancel(task.id, while_working=True)

    await asyncio.wait_for(
        asyncio.gather(manager.process_tasks(), cancel_once_running()), timeout=5
    )

    final = await tasks.get_by_id(task.id)
    assert final.status == TaskStatus.CANCELLED
    assert final.attempts == 0


@pytest.mark.asyncio
async def test_a_cancelled_pending_task_is_never_claimed(tasks):
    manager = WorkerManager(tasks.sessions)
    handler = AsyncMock()
    manager.register_handler(TaskType.CLEAN, handler)
    task = await tasks.create(Task(type=TaskType.CLEAN))
    async with tasks.sessions() as session:
        assert await SQLiteTaskRepository(session).cancel(task.id)

    await manager.process_tasks()

    handler.assert_not_awaited()
    assert (await tasks.get_by_id(task.id)).status == TaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancelling_does_not_touch_a_finished_task(tasks):
    task = await tasks.create(Task(type=TaskType.CLEAN, status=TaskStatus.DONE))
    async with tasks.sessions() as session:
        assert not await SQLiteTaskRepository(session).cancel(task.id, while_working=True)
    assert (await tasks.get_by_id(task.id)).status == TaskStatus.DONE
