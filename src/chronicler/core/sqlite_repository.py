from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete as sa_delete
from chronicler.core.models import Chronicle
from chronicler.core.database import DBChronicle, DBTask
from chronicler.core.repositories import ChronicleRepository, TaskRepository

class SQLiteChronicleRepository(ChronicleRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self) -> List[Chronicle]:
        result = await self.session.execute(select(DBChronicle))
        db_chronicles = result.scalars().all()
        return [Chronicle.model_validate(db) for db in db_chronicles]

    async def get_by_id(self, chronicle_id: UUID) -> Optional[Chronicle]:
        result = await self.session.execute(
            select(DBChronicle).where(DBChronicle.id == str(chronicle_id))
        )
        db_chronicle = result.scalar_one_or_none()
        return Chronicle.model_validate(db_chronicle) if db_chronicle else None

    async def create(self, chronicle: Chronicle) -> Chronicle:
        db_chronicle = DBChronicle(
            id=str(chronicle.id),
            title=chronicle.title,
            description=chronicle.description,
            source_file=chronicle.source_file,
            created_at=chronicle.created_at,
            updated_at=chronicle.updated_at
        )
        self.session.add(db_chronicle)
        await self.session.commit()
        await self.session.refresh(db_chronicle)
        return Chronicle.model_validate(db_chronicle)

    async def update(self, chronicle: Chronicle) -> Chronicle:
        result = await self.session.execute(
            select(DBChronicle).where(DBChronicle.id == str(chronicle.id))
        )
        db_chronicle = result.scalar_one_or_none()
        if db_chronicle:
            db_chronicle.title = chronicle.title
            db_chronicle.description = chronicle.description
            db_chronicle.source_file = chronicle.source_file
            db_chronicle.updated_at = chronicle.updated_at
            await self.session.commit()
            await self.session.refresh(db_chronicle)
            return Chronicle.model_validate(db_chronicle)
        raise ValueError(f"Chronicle {chronicle.id} not found")

    async def delete(self, chronicle_id: UUID) -> None:
        await self.session.execute(
            sa_delete(DBChronicle).where(DBChronicle.id == str(chronicle_id))
        )
        await self.session.commit()

class SQLiteTaskRepository(TaskRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self) -> List[dict]:
        result = await self.session.execute(select(DBTask))
        db_tasks = result.scalars().all()
        return [
            {
                "id": t.id,
                "type": t.type,
                "status": t.status,
                "priority": t.priority,
                "data": t.data,
                "error": t.error,
                "created_at": t.created_at,
                "updated_at": t.updated_at,
                "chronicle_id": t.chronicle_id,
            }
            for t in db_tasks
        ]

    async def create(self, task_data: dict) -> dict:
        db_task = DBTask(
            type=task_data["type"],
            status=task_data.get("status", "PENDING"),
            priority=task_data.get("priority", 0),
            data=task_data.get("data"),
            chronicle_id=task_data.get("chronicle_id"),
        )
        self.session.add(db_task)
        await self.session.commit()
        await self.session.refresh(db_task)
        return {
            "id": db_task.id,
            "type": db_task.type,
            "status": db_task.status,
            "priority": db_task.priority,
            "data": db_task.data,
            "created_at": db_task.created_at,
            "updated_at": db_task.updated_at,
            "chronicle_id": db_task.chronicle_id,
        }

    async def update_status(self, task_id: UUID, status: str, error: Optional[str] = None) -> None:
        result = await self.session.execute(
            select(DBTask).where(DBTask.id == str(task_id))
        )
        db_task = result.scalar_one_or_none()
        if db_task:
            db_task.status = status
            db_task.error = error
            await self.session.commit()
