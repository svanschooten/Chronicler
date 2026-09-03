from uuid import UUID

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
            await self.session.flush()
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
        await self.session.flush()
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
        await self.session.flush()

    async def update_line(
        self,
        line_id: UUID,
        text: str | None = None,
        speaker_id: UUID | None = None,
    ) -> TranscriptLine:
        """
        Edits one line in place. Timings are never touched: a corrected word must not
        shift the line off the audio it came from. See docs/transcript-editing.md.
        """
        db_line = await self.session.get(DBTranscriptLine, str(line_id))
        if db_line is None:
            raise KeyError(f"No transcript line {line_id}")

        if text is not None:
            db_line.text = text
        if speaker_id is not None:
            db_line.speaker_id = str(speaker_id)

        await self.session.flush()
        await self.session.refresh(db_line)

        line = TranscriptLine.model_validate(db_line)
        if db_line.speaker:
            line.speaker_name = db_line.speaker.name
        return line

    async def delete_line(self, line_id: UUID) -> None:
        """The speaker row is left alone - it still maps an audio source to a name."""
        db_line = await self.session.get(DBTranscriptLine, str(line_id))
        if db_line is None:
            raise KeyError(f"No transcript line {line_id}")
        await self.session.delete(db_line)
        await self.session.flush()

    async def delete_all_lines(self) -> None:
        await self.session.execute(sa_delete(DBTranscriptLine))

    async def delete_lines_by_speaker(self, speaker_id: UUID) -> None:
        await self.session.execute(
            sa_delete(DBTranscriptLine).where(DBTranscriptLine.speaker_id == str(speaker_id))
        )

    async def search(self, query: str) -> list[TranscriptLine]:
        raise NotImplementedError("Transcript full-text search is not implemented yet")
