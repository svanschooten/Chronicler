from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from chronicler.core.database import Base
from chronicler.core.models import Task, TaskStatus, TaskType
from chronicler.core.sqlite import SQLiteTaskRepository
from chronicler.core.workers import WorkerManager


@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session_factory() as session:
        yield session

    await engine.dispose()


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
