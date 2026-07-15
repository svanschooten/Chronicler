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

    task = await repo.create(Task(type=TaskType.IMPORT))

    await manager.process_tasks()

    fetched = await repo.get_by_id(task.id)
    assert fetched.status == TaskStatus.FAILED
    assert "Execution failed" in fetched.error
