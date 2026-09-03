from unittest.mock import MagicMock

import flet
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from chronicler.core.config import CONFIG_FILE_ENV_VAR, get_settings
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


@pytest.fixture
def isolated_config(monkeypatch, tmp_path):
    """
    Keeps Settings() away from the developer's real configuration.

    Without this, any test that reads or writes settings passes or fails depending on
    whose machine it runs on. Yields the config file's directory.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(home / "settings.yaml"))
    get_settings.cache_clear()
    yield home
    get_settings.cache_clear()
