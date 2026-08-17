from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import CursorResult, or_, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.database import DBChronicle, DBTask
from chronicler.core.models import Task, TaskStatus
from chronicler.core.repositories import TaskRepository
from chronicler.core.sqlite.patterns import LIKE_ESCAPE, contains_pattern

# How many PENDING candidates to consider per claim_next() call before giving up and
# waiting for the next poll cycle. Guards against pathologically unlucky contention
# without looping forever; in practice a single caller almost always claims its first
# candidate.
_MAX_CLAIM_CANDIDATES = 5


class SQLiteTaskRepository(TaskRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self) -> list[Task]:
        result = await self.session.execute(select(DBTask).order_by(DBTask.created_at.desc()))
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
            attempts=task.attempts,
            max_attempts=task.max_attempts,
        )
        self.session.add(db_task)
        await self.session.commit()
        await self.session.refresh(db_task)
        return Task.model_validate(db_task)

    async def claim_next(self, worker_id: str) -> Task | None:
        result = await self.session.execute(
            select(DBTask.id)
            .where(DBTask.status == TaskStatus.PENDING)
            .order_by(DBTask.priority.desc(), DBTask.created_at.asc())
            .limit(_MAX_CLAIM_CANDIDATES)
        )
        candidate_ids = [row[0] for row in result.all()]

        now = datetime.now()
        for candidate_id in candidate_ids:
            update_result = cast(
                CursorResult,
                await self.session.execute(
                    sa_update(DBTask)
                    .where(DBTask.id == candidate_id, DBTask.status == TaskStatus.PENDING)
                    .values(status=TaskStatus.WORKING, claimed_by=worker_id, claimed_at=now)
                ),
            )
            await self.session.commit()
            if update_result.rowcount == 1:
                return await self.get_by_id(UUID(candidate_id))
            # rowcount == 0: another worker claimed this candidate between our SELECT
            # and this UPDATE. Try the next candidate rather than returning None
            # outright - there may still be unclaimed work.

        return None

    async def mark_failed_or_retry(self, task_id: UUID, error: str) -> None:
        result = await self.session.execute(select(DBTask).where(DBTask.id == str(task_id)))
        db_task = result.scalar_one_or_none()
        if db_task:
            db_task.attempts += 1
            db_task.error = error
            if db_task.attempts < db_task.max_attempts:
                db_task.status = TaskStatus.PENDING
                db_task.claimed_by = None
                db_task.claimed_at = None
                db_task.progress = 0
            else:
                db_task.status = TaskStatus.FAILED
            await self.session.commit()

    async def update_status(self, task_id: UUID, status: str, error: str | None = None) -> None:
        result = await self.session.execute(select(DBTask).where(DBTask.id == str(task_id)))
        db_task = result.scalar_one_or_none()
        if db_task:
            db_task.status = status
            db_task.error = error
            if status == TaskStatus.PENDING:
                # Returning a task to the queue means it hasn't been attempted from the
                # queue's point of view: the previous run's error, progress and claim are
                # all stale. Same clearing mark_failed_or_retry() does for the same
                # transition - leaving claimed_by/claimed_at behind made the Tasks view
                # keep showing the *previous* run's start time until something claimed
                # it again.
                db_task.progress = 0
                db_task.error = None
                db_task.claimed_by = None
                db_task.claimed_at = None
            await self.session.commit()

    async def update_progress(self, task_id: UUID, progress: int) -> None:
        result = await self.session.execute(select(DBTask).where(DBTask.id == str(task_id)))
        db_task = result.scalar_one_or_none()
        if db_task:
            db_task.progress = progress
            await self.session.commit()

    async def search(self, query: str) -> list[Task]:
        pattern = contains_pattern(query)
        result = await self.session.execute(
            select(DBTask)
            .outerjoin(DBChronicle)
            .where(
                or_(
                    DBTask.type.ilike(pattern, escape=LIKE_ESCAPE),
                    DBChronicle.title.ilike(pattern, escape=LIKE_ESCAPE),
                )
            )
            .order_by(DBTask.created_at.desc())
        )
        db_tasks = result.scalars().all()
        return [Task.model_validate(t) for t in db_tasks]
