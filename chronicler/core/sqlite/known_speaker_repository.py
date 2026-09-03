from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.database import DBKnownSpeaker
from chronicler.core.models import KnownSpeaker
from chronicler.core.repositories import KnownSpeakerRepository
from chronicler.core.sqlite.patterns import LIKE_ESCAPE, contains_pattern


def normalize_speaker_name(name: str) -> str:
    return " ".join(name.split()).casefold()


class SQLiteKnownSpeakerRepository(KnownSpeakerRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def register(self, name: str) -> KnownSpeaker | None:
        cleaned = " ".join(name.split())
        if not cleaned:
            return None

        normalized = normalize_speaker_name(cleaned)
        result = await self.session.execute(
            select(DBKnownSpeaker).where(DBKnownSpeaker.normalized_name == normalized)
        )
        row = result.scalar_one_or_none()

        if row is None:
            row = DBKnownSpeaker(
                name=cleaned,
                normalized_name=normalized,
                uses=1,
                first_seen=datetime.now(),
                last_used=datetime.now(),
            )
            self.session.add(row)
        else:
            row.uses += 1
            row.last_used = datetime.now()

        await self.session.flush()
        await self.session.refresh(row)
        return KnownSpeaker.model_validate(row)

    async def list_speakers(self) -> list[KnownSpeaker]:
        result = await self.session.execute(
            select(DBKnownSpeaker).order_by(DBKnownSpeaker.normalized_name)
        )
        return [KnownSpeaker.model_validate(row) for row in result.scalars().all()]

    async def list_names(self) -> list[str]:
        return [speaker.name for speaker in await self.list_speakers()]

    async def search(self, query: str) -> list[str]:
        result = await self.session.execute(
            select(DBKnownSpeaker)
            .where(DBKnownSpeaker.name.ilike(contains_pattern(query), escape=LIKE_ESCAPE))
            .order_by(DBKnownSpeaker.normalized_name)
        )
        return [row.name for row in result.scalars().all()]
