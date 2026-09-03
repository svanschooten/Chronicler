from uuid import UUID

from sqlalchemy import delete as sa_delete
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.database import DBChronicle, DBTag, DBTask, chronicle_tags
from chronicler.core.models import Chronicle
from chronicler.core.repositories import ChronicleRepository
from chronicler.core.sqlite.patterns import LIKE_ESCAPE, contains_pattern


class SQLiteChronicleRepository(ChronicleRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self) -> list[Chronicle]:
        result = await self.session.execute(
            select(DBChronicle).order_by(DBChronicle.created_at.desc())
        )
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
            kind=chronicle.kind,
            status=chronicle.status,
            source_file=chronicle.source_file,
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
            db_chronicle.source_file = chronicle.source_file
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
        result = await self.session.execute(
            select(DBChronicle).where(DBChronicle.id == str(chronicle_id))
        )
        db_chronicle = result.scalar_one_or_none()
        if not db_chronicle:
            raise ValueError(f"Chronicle {chronicle_id} not found")

        tag_result = await self.session.execute(select(DBTag).where(DBTag.name == tag_name))
        db_tag = tag_result.scalar_one_or_none()
        if not db_tag:
            db_tag = DBTag(name=tag_name)
            self.session.add(db_tag)
            await self.session.flush()

        if db_tag not in db_chronicle.tags:
            db_chronicle.tags.append(db_tag)
            await self.session.commit()
