import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from chronicler.core.database import Base
from chronicler.core.models import Chronicle
from chronicler.core.sqlite_repository import SQLiteChronicleRepository
from uuid import uuid4

import pytest_asyncio

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
