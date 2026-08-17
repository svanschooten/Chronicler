from unittest.mock import MagicMock

import flet
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from chronicler.core.database import Base


@pytest.fixture(autouse=True)
def mock_flet_app(monkeypatch):
    """Keeps any accidental attempt to actually launch a Flet window from opening one
    during a test run. Both names are patched because which one exists varies by Flet
    version."""
    monkeypatch.setattr(flet, "app", MagicMock())
    if hasattr(flet, "run"):
        monkeypatch.setattr(flet, "run", MagicMock())


@pytest_asyncio.fixture
async def async_session():
    """An in-memory archive database session.

    Shared here rather than redefined per module - it was copy-pasted identically
    across four test modules, which is four places to update whenever the archive
    schema setup changes. Project (per-chronicle) databases are not this schema; tests
    that need one go through DatabaseManager instead.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()
