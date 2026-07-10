from uuid import UUID

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.database import DBChronicle, DBTask
from chronicler.core.models import Chronicle, Task, TaskStatus
from chronicler.core.repositories import ChronicleRepository, TaskRepository


class SQLiteChronicleRepository(ChronicleRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self) -> list[Chronicle]:
        result = await self.session.execute(select(DBChronicle))
        db_chronicles = result.scalars().all()
        return [Chronicle.model_validate(db) for db in db_chronicles]

    async def get_by_id(self, chronicle_id: UUID) -> Chronicle | None:
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
            updated_at=chronicle.updated_at,
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

    async def get_all(self) -> list[Task]:
        result = await self.session.execute(select(DBTask))
        db_tasks = result.scalars().all()
        return [Task.model_validate(t) for t in db_tasks]

    async def get_pending(self) -> list[Task]:
        result = await self.session.execute(
            select(DBTask)
            .where(DBTask.status == TaskStatus.PENDING)
            .order_by(DBTask.priority.desc(), DBTask.created_at.asc())
        )
        db_tasks = result.scalars().all()
        return [Task.model_validate(t) for t in db_tasks]

    async def get_by_id(self, task_id: UUID) -> Task | None:
        result = await self.session.execute(select(DBTask).where(DBTask.id == str(task_id)))
        db_task = result.scalar_one_or_none()
        return Task.model_validate(db_task) if db_task else None

    async def create(self, task: Task) -> Task:
        db_task = DBTask(
            id=str(task.id),
            type=task.type,
            status=task.status,
            priority=task.priority,
            progress=task.progress,
            data=task.data,
            chronicle_id=str(task.chronicle_id) if task.chronicle_id else None,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )
        self.session.add(db_task)
        await self.session.commit()
        await self.session.refresh(db_task)
        return Task.model_validate(db_task)

    async def update_status(self, task_id: UUID, status: str, error: str | None = None) -> None:
        result = await self.session.execute(select(DBTask).where(DBTask.id == str(task_id)))
        db_task = result.scalar_one_or_none()
        if db_task:
            db_task.status = status
            db_task.error = error
            if status == TaskStatus.PENDING:
                db_task.progress = 0
                db_task.error = None
            await self.session.commit()

    async def update_progress(self, task_id: UUID, progress: int) -> None:
        result = await self.session.execute(select(DBTask).where(DBTask.id == str(task_id)))
        db_task = result.scalar_one_or_none()
        if db_task:
            db_task.progress = progress
            await self.session.commit()
