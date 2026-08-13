from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from chronicler.core.database import Base
from chronicler.core.models import Task, TaskStatus, TaskType
from chronicler.core.sqlite import SQLiteTaskRepository
from chronicler.core.workers import WorkerManager, perform_test_task


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
async def test_test_worker_execution(async_session):
    repo = SQLiteTaskRepository(async_session)
    manager = WorkerManager(repo)
    manager.register_handler(TaskType.TEST, perform_test_task)

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
    # max_attempts=1: this test is about failure recording, not retry - see
    # tests/chronicler/core/test_workers.py for the retry-specific tests.
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
