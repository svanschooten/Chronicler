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
    """Run one migration chain ("archive" or "project") to head against an
    already-open sync connection - see chronicler/migrations/<chain>/env.py, which
    picks this connection up via config.attributes["connection"] instead of opening
    its own engine. No static alembic.ini: the project chain runs against a different
    project.db file per chronicle, so there's no single fixed URL to put in a config
    file - the already-open connection carries that instead.
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

    async def init_archive(self):
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        (self.workspace_path / "imports").mkdir(parents=True, exist_ok=True)
        async with self.archive_engine.begin() as conn:
            await conn.run_sync(_run_alembic_upgrade, "archive")

    def get_imports_path(self) -> Path:
        path = self.workspace_path / "imports"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_archive_session(self) -> AsyncSession:
        return self.archive_session_factory()

    async def get_project_session(
        self, chronicle_id: str, custom_path: Path | None = None
    ) -> AsyncSession:
        if chronicle_id not in self._project_engines:
            if custom_path:
                project_db_path = custom_path
            else:
                project_db_path = self.workspace_path / "chronicles" / chronicle_id / "project.db"

            project_db_path.parent.mkdir(parents=True, exist_ok=True)

            engine = create_async_engine(f"sqlite+aiosqlite:///{project_db_path}")
            async with engine.begin() as conn:
                await conn.run_sync(_run_alembic_upgrade, "project")
            self._project_engines[chronicle_id] = engine

        engine = self._project_engines[chronicle_id]
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        return session_factory()

    async def close_all(self):
        await self.archive_engine.dispose()
        for engine in self._project_engines.values():
            await engine.dispose()
        self._project_engines.clear()
