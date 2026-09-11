import asyncio
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)

_MIGRATIONS_ROOT = Path(__file__).resolve().parent.parent / "migrations"


def _run_alembic_upgrade(connection: Connection, chain: str) -> None:
    """
    Run one migration chain ("archive" or "project") to head against an already-open sync
    connection - see chronicler/migrations/<chain>/env.py, which picks this connection up
    via config.attributes["connection"] instead of opening its own engine.
    """
    logger.info(f"Running {chain} migrations")
    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_ROOT / chain))
    cfg.attributes["connection"] = connection
    command.upgrade(cfg, "head")


class DatabaseManager:
    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path
        self.archive_db_path = workspace_path / "chronicler.db"
        self.archive_engine = create_async_engine(f"sqlite+aiosqlite:///{self.archive_db_path}")
        self.archive_session_factory = async_sessionmaker(
            self.archive_engine, expire_on_commit=False
        )
        self._project_engines: dict[str, AsyncEngine] = {}
        self._migration_lock = asyncio.Lock()

    async def init_archive(self):
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        (self.workspace_path / "imports").mkdir(parents=True, exist_ok=True)
        async with self._migration_lock:
            async with self.archive_engine.begin() as conn:
                await conn.run_sync(_run_alembic_upgrade, "archive")

    def get_imports_path(self) -> Path:
        path = self.workspace_path / "imports"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_chronicle_sources_path(self, chronicle_id: str) -> Path:
        """
        Durable per-chronicle storage for audio sources (as opposed to
        get_imports_path()'s shared scratch space, which a worker is free to
        overwrite/lose).
        """
        return self.sources_path_for(chronicle_id)

    def sources_path_for(self, chronicle_id: str, project_path: Path | None = None) -> Path:
        """
        A chronicle's audio directory: beside a linked project.db, otherwise in the
        workspace. A linked chronicle's files were never in the workspace, so looking
        there made every one of its sources read as missing. See docs/storage.md.
        """
        root = (
            project_path.parent
            if project_path is not None
            else self.workspace_path / "chronicles" / chronicle_id
        )
        path = root / "sources"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_archive_session(self) -> AsyncSession:
        return self.archive_session_factory()

    async def get_project_session(
        self, chronicle_id: str, custom_path: Path | None = None
    ) -> AsyncSession:
        engine = await self._project_engine(chronicle_id, custom_path)
        return async_sessionmaker(engine, expire_on_commit=False)()

    async def _project_engine(
        self, chronicle_id: str, custom_path: Path | None = None
    ) -> AsyncEngine:
        """
        The engine for one chronicle, creating and migrating it at most once.

        One lock for every chronicle, not one per chronicle: Alembic drives migrations
        through a process-global proxy, so two chains running concurrently corrupt each
        other's context even when they target different files. See docs/storage.md.
        """
        engine = self._project_engines.get(chronicle_id)
        if engine is not None:
            return engine

        async with self._migration_lock:
            engine = self._project_engines.get(chronicle_id)
            if engine is not None:
                return engine

            if custom_path:
                project_db_path = custom_path
            else:
                project_db_path = self.workspace_path / "chronicles" / chronicle_id / "project.db"
            project_db_path.parent.mkdir(parents=True, exist_ok=True)

            engine = create_async_engine(f"sqlite+aiosqlite:///{project_db_path}")
            try:
                async with engine.begin() as conn:
                    await conn.run_sync(_run_alembic_upgrade, "project")
            except Exception:
                await engine.dispose()
                raise

            self._project_engines[chronicle_id] = engine
            return engine

    async def close_project(self, chronicle_id: str) -> None:
        """
        Releases one chronicle's project database, so its file can be moved or removed.

        The pool holds a connection open long after the session that used it was closed,
        and Windows refuses to delete a file anything still has open - which is why
        deleting a chronicle failed there and not on Linux. See docs/storage.md.
        """
        engine = self._project_engines.pop(chronicle_id, None)
        if engine is None:
            return
        logger.debug(f"Closing the project database for chronicle {chronicle_id}")
        await engine.dispose()

    async def close_all(self):
        await self.archive_engine.dispose()
        for engine in self._project_engines.values():
            await engine.dispose()
        self._project_engines.clear()
