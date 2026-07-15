from uuid import UUID

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.database import DBChronicle
from chronicler.core.models import Chronicle
from chronicler.core.repositories import ChronicleRepository


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
