from unittest.mock import MagicMock

import flet
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from chronicler.core.database import Base


@pytest.fixture(autouse=True)
def mock_flet_app(monkeypatch):
    """
    Keeps any accidental attempt to actually launch a Flet window from opening one during a
    test run.
    """
    monkeypatch.setattr(flet, "app", MagicMock())
    if hasattr(flet, "run"):
        monkeypatch.setattr(flet, "run", MagicMock())


@pytest_asyncio.fixture
async def async_session():
    """An in-memory archive database session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()
