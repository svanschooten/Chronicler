from uuid import UUID

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.models import Summary
from chronicler.core.project_database import DBSummary


class SQLiteSummaryRepository:
    """Generated summaries for one chronicle, numbered so several can be compared."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def next_number(self) -> int:
        result = await self.session.execute(select(func.max(DBSummary.number)))
        return int(result.scalar() or 0) + 1

    async def add(self, summary: Summary) -> Summary:
        row = DBSummary(
            id=str(summary.id),
            number=summary.number,
            title=summary.title,
            content=summary.content,
            model=summary.model,
            provider=summary.provider,
            prompt_template=summary.prompt_template,
            language=summary.language,
            created_at=summary.created_at,
            chunk_count=summary.chunk_count,
            prompt_tokens=summary.prompt_tokens,
            completion_tokens=summary.completion_tokens,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return Summary.model_validate(row)

    async def list_summaries(self) -> list[Summary]:
        result = await self.session.execute(select(DBSummary).order_by(DBSummary.number))
        return [Summary.model_validate(row) for row in result.scalars().all()]

    async def get(self, summary_id: UUID) -> Summary | None:
        result = await self.session.execute(
            select(DBSummary).where(DBSummary.id == str(summary_id))
        )
        row = result.scalar_one_or_none()
        return Summary.model_validate(row) if row else None

    async def delete(self, summary_id: UUID) -> None:
        await self.session.execute(sa_delete(DBSummary).where(DBSummary.id == str(summary_id)))

    async def count(self) -> int:
        result = await self.session.execute(select(func.count(DBSummary.id)))
        return int(result.scalar() or 0)
