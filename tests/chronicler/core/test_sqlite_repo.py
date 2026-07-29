import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from chronicler.core.database import Base
from chronicler.core.models import Chronicle, Task, TaskStatus, TaskType
from chronicler.core.sqlite import SQLiteChronicleRepository, SQLiteTaskRepository


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
async def test_create_and_get_chronicle(async_session):
    repo = SQLiteChronicleRepository(async_session)
    chronicle = Chronicle(title="Test Chronicle")

    created = await repo.create(chronicle)
    assert created.id == chronicle.id
    assert created.title == "Test Chronicle"

    fetched = await repo.get_by_id(chronicle.id)
    assert fetched is not None
    assert fetched.id == chronicle.id
    assert fetched.title == "Test Chronicle"


@pytest.mark.asyncio
async def test_get_all_chronicles(async_session):
    repo = SQLiteChronicleRepository(async_session)
    await repo.create(Chronicle(title="C1"))
    await repo.create(Chronicle(title="C2"))

    all_chronicles = await repo.get_all()
    assert len(all_chronicles) == 2
    assert {c.title for c in all_chronicles} == {"C1", "C2"}


@pytest.mark.asyncio
async def test_update_chronicle(async_session):
    repo = SQLiteChronicleRepository(async_session)
    chronicle = await repo.create(Chronicle(title="Old Title"))

    chronicle.title = "New Title"
    updated = await repo.update(chronicle)
    assert updated.title == "New Title"

    fetched = await repo.get_by_id(chronicle.id)
    assert fetched.title == "New Title"


@pytest.mark.asyncio
async def test_delete_chronicle(async_session):
    repo = SQLiteChronicleRepository(async_session)
    chronicle = await repo.create(Chronicle(title="To be deleted"))

    await repo.delete(chronicle.id)
    fetched = await repo.get_by_id(chronicle.id)
    assert fetched is None


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
async def test_search_chronicles(async_session):
    repo = SQLiteChronicleRepository(async_session)
    await repo.create(Chronicle(title="Meeting One"))
    await repo.create(Chronicle(title="Interview Two"))

    results = await repo.search("Meeting")
    assert len(results) == 1
    assert results[0].title == "Meeting One"

    results = await repo.search("One")
    assert len(results) == 1
    assert results[0].title == "Meeting One"

    results = await repo.search("Three")
    assert len(results) == 0


@pytest.mark.asyncio
async def test_search_tasks(async_session):
    chronicle_repo = SQLiteChronicleRepository(async_session)
    task_repo = SQLiteTaskRepository(async_session)

    chronicle = await chronicle_repo.create(Chronicle(title="D&D Session"))

    await task_repo.create(Task(type=TaskType.IMPORT, chronicle_id=chronicle.id))
    await task_repo.create(Task(type=TaskType.TRANSCRIBE))

    # Search by type
    results = await task_repo.search("IMPORT")
    assert len(results) == 1
    assert results[0].type == TaskType.IMPORT

    # Search by chronicle title
    results = await task_repo.search("D&D")
    assert len(results) == 1
    assert results[0].type == TaskType.IMPORT

    # Search case insensitive
    results = await task_repo.search("d&d")
    assert len(results) == 1
