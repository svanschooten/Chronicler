"""Test helpers for putting a chronicle's row in the archive, which is where its location lives."""

from pathlib import Path
from uuid import UUID

from sqlalchemy import delete

from chronicler.core.database import Base, DBChronicle
from chronicler.core.database_manager import DatabaseManager


async def register_chronicle(
    db_manager: DatabaseManager, chronicle_id: UUID | str, project_path: Path | None = None
) -> None:
    """
    Records a chronicle in the archive, linked to `project_path` when given, so its project
    database can be opened by id. Creates the archive tables if the test has not.
    """
    db_manager.workspace_path.mkdir(parents=True, exist_ok=True)
    async with db_manager.archive_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with db_manager.get_archive_session() as session:
        if await session.get(DBChronicle, str(chronicle_id)) is None:
            session.add(
                DBChronicle(
                    id=str(chronicle_id),
                    title="Test chronicle",
                    project_path=str(project_path) if project_path else None,
                )
            )
            await session.commit()


async def forget_chronicle(db_manager: DatabaseManager, chronicle_id: UUID | str) -> None:
    """Removes what `register_chronicle` added, for a chronicle that was only a staging area."""
    async with db_manager.get_archive_session() as session:
        await session.execute(delete(DBChronicle).where(DBChronicle.id == str(chronicle_id)))
        await session.commit()
    await db_manager.close_project(str(chronicle_id))
