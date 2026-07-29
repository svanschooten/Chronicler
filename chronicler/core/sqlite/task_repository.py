from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.database import DBChronicle, DBTask
from chronicler.core.models import Task, TaskStatus
from chronicler.core.repositories import TaskRepository


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

    async def search(self, query: str) -> list[Task]:
        result = await self.session.execute(
            select(DBTask)
            .outerjoin(DBChronicle)
            .where(or_(DBTask.type.ilike(f"%{query}%"), DBChronicle.title.ilike(f"%{query}%")))
        )
        db_tasks = result.scalars().all()
        return [Task.model_validate(t) for t in db_tasks]
