from collections.abc import AsyncIterator
from dataclasses import dataclass
from unittest.mock import MagicMock

import flet
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from chronicler.core.config import CONFIG_FILE_ENV_VAR, get_settings
from chronicler.core.database import Base
from chronicler.core.database_manager import DatabaseManager
from tests.isolation import isolate_home

LOCK_TIMEOUT = 0.2
"""Seconds `two_sessions` waits on a lock, so contention tests fail fast instead of in 5s."""


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


@dataclass
class TwoSessions:
    """A file-backed workspace and two independent connections to its `chronicler.db`."""

    db_manager: DatabaseManager
    first: AsyncSession
    second: AsyncSession


@pytest_asyncio.fixture
async def two_sessions(tmp_path) -> AsyncIterator[TwoSessions]:
    """
    Two sessions on one real workspace database, for tests that need a write lock.

    `async_session` is a single in-memory connection, where nothing can ever wait on a
    lock. Here a flushed, uncommitted write in `first` makes a write in `second` raise
    "database is locked" after `LOCK_TIMEOUT`. `db_manager` uses the same timeout, so
    code under test that opens its own sessions fails just as fast.
    """
    db_manager = DatabaseManager(tmp_path / "workspace", busy_timeout=LOCK_TIMEOUT)
    await db_manager.init_archive()
    async with (
        db_manager.get_archive_session() as first,
        db_manager.get_archive_session() as second,
    ):
        yield TwoSessions(db_manager, first, second)
    await db_manager.close_all()


@pytest.fixture
def isolated_config(monkeypatch, tmp_path):
    """
    Keeps Settings() away from the developer's real configuration.

    Without this, any test that reads or writes settings passes or fails depending on
    whose machine it runs on. Yields the config file's directory.
    """
    home = tmp_path / "home"
    home.mkdir()
    isolate_home(monkeypatch, home)
    monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(home / "settings.yaml"))
    get_settings.cache_clear()
    yield home
    get_settings.cache_clear()
