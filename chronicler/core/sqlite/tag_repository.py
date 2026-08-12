from uuid import UUID

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.database import DBTag
from chronicler.core.models import Tag
from chronicler.core.repositories import TagRepository


class SQLiteTagRepository(TagRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self) -> list[Tag]:
        result = await self.session.execute(select(DBTag))
        db_tags = result.scalars().all()
        return [Tag.model_validate(t) for t in db_tags]

    async def create(self, tag: Tag) -> Tag:
        db_tag = DBTag(
            id=str(tag.id),
            name=tag.name,
            color=tag.color,
        )
        self.session.add(db_tag)
        await self.session.commit()
        await self.session.refresh(db_tag)
        return Tag.model_validate(db_tag)

    async def delete(self, tag_id: UUID) -> None:
        await self.session.execute(sa_delete(DBTag).where(DBTag.id == str(tag_id)))
        await self.session.commit()

    async def search(self, query: str) -> list[Tag]:
        result = await self.session.execute(select(DBTag).where(DBTag.name.ilike(f"%{query}%")))
        db_tags = result.scalars().all()
        return [Tag.model_validate(t) for t in db_tags]
