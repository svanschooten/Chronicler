from uuid import UUID

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.database import DBChronicle, DBTag, DBTask, chronicle_tags
from chronicler.core.models import Chronicle
from chronicler.core.sqlite.patterns import LIKE_ESCAPE, contains_pattern


class SQLiteChronicleRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self) -> list[Chronicle]:
        result = await self.session.execute(
            select(DBChronicle).order_by(DBChronicle.created_at.desc())
        )
        db_chronicles = result.scalars().all()
        return [Chronicle.model_validate(db) for db in db_chronicles]

    async def count(self) -> int:
        result = await self.session.execute(select(func.count()).select_from(DBChronicle))
        return int(result.scalar_one())

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
            kind=chronicle.kind,
            status=chronicle.status,
            project_path=chronicle.project_path,
            duration=chronicle.duration,
            speakers_count=chronicle.speakers_count,
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
            db_chronicle.kind = chronicle.kind
            db_chronicle.status = chronicle.status
            db_chronicle.project_path = chronicle.project_path
            db_chronicle.duration = chronicle.duration
            db_chronicle.speakers_count = chronicle.speakers_count
            db_chronicle.updated_at = chronicle.updated_at
            await self.session.commit()
            await self.session.refresh(db_chronicle)
            return Chronicle.model_validate(db_chronicle)
        raise ValueError(f"Chronicle {chronicle.id} not found")

    async def delete(self, chronicle_id: UUID) -> None:
        await self.session.execute(
            sa_delete(chronicle_tags).where(chronicle_tags.c.chronicle_id == str(chronicle_id))
        )
        await self.session.execute(
            sa_delete(DBTask).where(DBTask.chronicle_id == str(chronicle_id))
        )
        await self.session.execute(
            sa_delete(DBChronicle).where(DBChronicle.id == str(chronicle_id))
        )
        await self.session.commit()

    async def search(self, query: str) -> list[Chronicle]:
        """Chronicles whose title, description or any tag name contains `query`."""
        pattern = contains_pattern(query)
        tagged = (
            select(chronicle_tags.c.chronicle_id)
            .join(DBTag, DBTag.id == chronicle_tags.c.tag_id)
            .where(DBTag.name.ilike(pattern, escape=LIKE_ESCAPE))
        )
        result = await self.session.execute(
            select(DBChronicle)
            .where(
                or_(
                    DBChronicle.title.ilike(pattern, escape=LIKE_ESCAPE),
                    DBChronicle.description.ilike(pattern, escape=LIKE_ESCAPE),
                    DBChronicle.id.in_(tagged),
                )
            )
            .order_by(DBChronicle.created_at.desc())
        )
        db_chronicles = result.scalars().all()
        return [Chronicle.model_validate(db) for db in db_chronicles]

    async def add_tag(self, chronicle_id: UUID, tag_name: str) -> None:
        """
        Attach a tag to a chronicle, creating the tag if no tag has this name yet. Names
        match without regard to case, so "Product" attaches the existing "product".
        """
        result = await self.session.execute(
            select(DBChronicle).where(DBChronicle.id == str(chronicle_id))
        )
        db_chronicle = result.scalar_one_or_none()
        if not db_chronicle:
            raise ValueError(f"Chronicle {chronicle_id} not found")

        tag_result = await self.session.execute(
            select(DBTag).where(func.lower(DBTag.name) == tag_name.casefold())
        )
        db_tag = tag_result.scalar_one_or_none()
        if not db_tag:
            db_tag = DBTag(name=tag_name)
            self.session.add(db_tag)
            await self.session.flush()

        if db_tag not in db_chronicle.tags:
            db_chronicle.tags.append(db_tag)
            await self.session.commit()

    async def remove_tag(self, chronicle_id: UUID, tag_name: str) -> None:
        """
        Detaches a tag from a chronicle, and deletes the tag once no chronicle has it, so
        the workspace does not collect tags nothing uses. A tag the chronicle does not
        have is left alone.
        """
        result = await self.session.execute(
            select(DBChronicle).where(DBChronicle.id == str(chronicle_id))
        )
        db_chronicle = result.scalar_one_or_none()
        if not db_chronicle:
            raise ValueError(f"Chronicle {chronicle_id} not found")

        db_tag = next(
            (tag for tag in db_chronicle.tags if tag.name.casefold() == tag_name.casefold()), None
        )
        if db_tag is None:
            return
        db_chronicle.tags.remove(db_tag)
        await self.session.flush()

        still_used = await self.session.execute(
            select(func.count())
            .select_from(chronicle_tags)
            .where(chronicle_tags.c.tag_id == db_tag.id)
        )
        if not still_used.scalar_one():
            await self.session.delete(db_tag)
        await self.session.commit()
