import logging
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from chronicler.core.database import Base as ArchiveBase
from chronicler.core.project_database import ProjectBase

logger = logging.getLogger(__name__)


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
            await conn.run_sync(ArchiveBase.metadata.create_all)
            await conn.run_sync(self._migrate_schema_sync, ArchiveBase)

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
                await conn.run_sync(ProjectBase.metadata.create_all)
                await conn.run_sync(self._migrate_schema_sync, ProjectBase)
            self._project_engines[chronicle_id] = engine

        engine = self._project_engines[chronicle_id]
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        return session_factory()

    def _migrate_schema_sync(self, conn, base):
        inspector = inspect(conn)
        for table_name, table in base.metadata.tables.items():
            if table_name not in inspector.get_table_names():
                continue

            existing_columns = {c["name"] for c in inspector.get_columns(table_name)}
            for column in table.columns:
                if column.name not in existing_columns:
                    logger.info(f"Adding missing column {column.name} to table {table_name}")
                    # Basic SQLite column addition
                    type_str = str(column.type.compile(dialect=conn.dialect))

                    # Handle defaults for NOT NULL columns in SQLite
                    default_str = ""
                    if not column.nullable:
                        if column.default is not None and not callable(column.default.arg):
                            val = column.default.arg
                            if isinstance(val, str):
                                default_str = f" DEFAULT '{val}'"
                            else:
                                default_str = f" DEFAULT {val}"
                        elif "INT" in type_str.upper():
                            default_str = " DEFAULT 0"
                        elif "VARCHAR" in type_str.upper() or "TEXT" in type_str.upper():
                            default_str = " DEFAULT ''"
                        else:
                            # If it's NOT NULL but we don't know a good default,
                            # SQLite might complain if there are existing rows.
                            # But for this app, these defaults should cover most cases.
                            default_str = " DEFAULT ''"

                    query = (
                        f"ALTER TABLE {table_name} ADD COLUMN {column.name} {type_str}{default_str}"
                    )
                    conn.execute(text(query))

    async def close_all(self):
        await self.archive_engine.dispose()
        for engine in self._project_engines.values():
            await engine.dispose()
        self._project_engines.clear()
