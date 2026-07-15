from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from chronicler.core.database import Base as ArchiveBase
from chronicler.core.project_database import ProjectBase


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
        async with self.archive_engine.begin() as conn:
            await conn.run_sync(ArchiveBase.metadata.create_all)

    def get_archive_session(self) -> AsyncSession:
        return self.archive_session_factory()

    async def get_project_session(self, chronicle_id: str) -> AsyncSession:
        if chronicle_id not in self._project_engines:
            project_db_path = self.workspace_path / "chronicles" / chronicle_id / "project.db"
            project_db_path.parent.mkdir(parents=True, exist_ok=True)

            engine = create_async_engine(f"sqlite+aiosqlite:///{project_db_path}")
            async with engine.begin() as conn:
                await conn.run_sync(ProjectBase.metadata.create_all)
            self._project_engines[chronicle_id] = engine

        engine = self._project_engines[chronicle_id]
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        return session_factory()

    async def close_all(self):
        await self.archive_engine.dispose()
        for engine in self._project_engines.values():
            await engine.dispose()
        self._project_engines.clear()
