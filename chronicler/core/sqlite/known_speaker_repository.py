from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.database import DBKnownSpeaker
from chronicler.core.models import KnownSpeaker
from chronicler.core.repositories import KnownSpeakerRepository


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
        try:
            result = await self.session.execute(
                select(DBKnownSpeaker).where(DBKnownSpeaker.normalized_name == normalized)
            )
            row = result.scalar_one_or_none()

            if row is None:
                row = DBKnownSpeaker(name=cleaned, normalized_name=normalized)
                self.session.add(row)

            # Commit here: a flush alone holds the workspace write lock until something
            # else happens to commit this session, and is lost if nothing does.
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        await self.session.refresh(row)
        return KnownSpeaker.model_validate(row)

    async def list_speakers(self) -> list[KnownSpeaker]:
        result = await self.session.execute(
            select(DBKnownSpeaker).order_by(DBKnownSpeaker.normalized_name)
        )
        return [KnownSpeaker.model_validate(row) for row in result.scalars().all()]

    async def list_names(self) -> list[str]:
        return [speaker.name for speaker in await self.list_speakers()]
