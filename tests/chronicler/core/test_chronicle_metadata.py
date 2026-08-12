import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from chronicler.core.database import Base
from chronicler.core.models import Chronicle
from chronicler.core.sqlite import SQLiteChronicleRepository


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
async def test_chronicle_project_path(async_session):
    repo = SQLiteChronicleRepository(async_session)
    chronicle = Chronicle(title="External Project", project_path="/external/path/project.db")

    created = await repo.create(chronicle)
    assert created.project_path == "/external/path/project.db"

    fetched = await repo.get_by_id(chronicle.id)
    assert fetched.project_path == "/external/path/project.db"


@pytest.mark.asyncio
async def test_chronicle_source_file(async_session):
    repo = SQLiteChronicleRepository(async_session)
    chronicle = Chronicle(title="Audio File", source_file="/path/to/audio.mp3")

    created = await repo.create(chronicle)
    assert created.source_file == "/path/to/audio.mp3"

    fetched = await repo.get_by_id(chronicle.id)
    assert fetched.source_file == "/path/to/audio.mp3"
