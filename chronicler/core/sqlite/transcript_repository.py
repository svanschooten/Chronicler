from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.models import Speaker, TranscriptLine
from chronicler.core.project_database import DBSpeaker, DBTranscriptLine
from chronicler.core.repositories import TranscriptRepository


class SQLiteTranscriptRepository(TranscriptRepository):

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_speakers(self) -> list[Speaker]:
        result = await self.session.execute(select(DBSpeaker))
        db_speakers = result.scalars().all()
        return [Speaker.model_validate(s) for s in db_speakers]

    async def get_or_create_speaker(self, name: str) -> Speaker:
        result = await self.session.execute(select(DBSpeaker).where(DBSpeaker.name == name))
        db_speaker = result.scalar_one_or_none()
        if not db_speaker:
            db_speaker = DBSpeaker(name=name)
            self.session.add(db_speaker)
            await self.session.commit()
            await self.session.refresh(db_speaker)
        return Speaker.model_validate(db_speaker)

    async def get_lines(self) -> list[TranscriptLine]:
        result = await self.session.execute(
            select(DBTranscriptLine).order_by(DBTranscriptLine.start_time)
        )
        db_lines = result.scalars().all()
        lines = []
        for db in db_lines:
            line = TranscriptLine.model_validate(db)
            if db.speaker:
                line.speaker_name = db.speaker.name
            lines.append(line)
        return lines

    async def add_line(self, line: TranscriptLine) -> TranscriptLine:
        db_line = DBTranscriptLine(
            id=str(line.id),
            speaker_id=str(line.speaker_id) if line.speaker_id else None,
            start_time=line.start_time,
            end_time=line.end_time,
            text=line.text,
        )
        self.session.add(db_line)
        await self.session.commit()
        await self.session.refresh(db_line)
        return TranscriptLine.model_validate(db_line)

    async def add_lines(self, lines: list[TranscriptLine]) -> None:
        db_lines = [
            DBTranscriptLine(
                id=str(line.id),
                speaker_id=str(line.speaker_id) if line.speaker_id else None,
                start_time=line.start_time,
                end_time=line.end_time,
                text=line.text,
            )
            for line in lines
        ]
        self.session.add_all(db_lines)
        await self.session.commit()

    async def delete_all(self) -> None:
        await self.session.execute(sa_delete(DBTranscriptLine))
        await self.session.execute(sa_delete(DBSpeaker))
        await self.session.commit()

    async def search(self, query: str) -> list[TranscriptLine]:
        pass # TODO implement search
