from uuid import UUID

from sqlalchemy import delete as sa_delete
from sqlalchemy import literal_column, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.models import Speaker, TranscriptLine
from chronicler.core.project_database import DBSpeaker, DBTranscriptLine
from chronicler.core.sqlite.known_speaker_repository import normalize_speaker_name
from chronicler.core.sqlite.patterns import fts_query

SEARCH_LIMIT = 200


class SQLiteTranscriptRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_speakers(self) -> list[Speaker]:
        result = await self.session.execute(select(DBSpeaker))
        db_speakers = result.scalars().all()
        return [Speaker.model_validate(s) for s in db_speakers]

    async def get_or_create_speaker(self, name: str) -> Speaker:
        """
        The speaker this name means in this chronicle, matched the way the workspace
        registry matches: whitespace collapsed and case folded, so typing `gm` where `GM`
        exists reuses `GM` instead of creating a second speaker. The first spelling seen
        is kept. Rows that already differ only in case are left alone; the oldest of them
        is the one matched. See docs/speakers.md.
        """
        cleaned = " ".join(name.split())
        wanted = normalize_speaker_name(cleaned)
        result = await self.session.execute(
            select(DBSpeaker).order_by(literal_column("speakers.rowid"))
        )
        db_speaker = next(
            (row for row in result.scalars() if normalize_speaker_name(row.name) == wanted),
            None,
        )
        if db_speaker is None:
            db_speaker = DBSpeaker(name=cleaned)
            self.session.add(db_speaker)
            await self.session.flush()
            await self.session.refresh(db_speaker)
        return Speaker.model_validate(db_speaker)

    async def get_lines(self) -> list[TranscriptLine]:
        result = await self.session.execute(
            select(DBTranscriptLine).order_by(DBTranscriptLine.start_time)
        )
        return self._to_lines(result.scalars().all())

    async def count_speakers(self) -> int:
        """
        The speakers with at least one line, counted in the database: what
        `reconcile.count_speakers` gives for `get_lines()`, without loading the transcript.
        Lines with no speaker count as one, as they do there.
        """
        result = await self.session.execute(
            select(DBSpeaker.name)
            .select_from(DBTranscriptLine)
            .outerjoin(DBSpeaker, DBTranscriptLine.speaker_id == DBSpeaker.id)
            .distinct()
        )
        return len(result.all())

    @staticmethod
    def _to_lines(db_lines) -> list[TranscriptLine]:
        lines = []
        for db in db_lines:
            line = TranscriptLine.model_validate(db)
            if db.speaker:
                line.speaker_name = db.speaker.name
            lines.append(line)
        return lines

    async def add_lines(self, lines: list[TranscriptLine]) -> None:
        db_lines = [
            DBTranscriptLine(
                id=str(line.id),
                speaker_id=str(line.speaker_id) if line.speaker_id else None,
                source_id=str(line.source_id) if line.source_id else None,
                start_time=line.start_time,
                end_time=line.end_time,
                text=line.text,
                synthetic_timing=line.synthetic_timing,
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
        """Delete every transcript line."""
        await self.session.execute(sa_delete(DBTranscriptLine))

    async def delete_track_lines(self, source_id: UUID) -> None:
        """
        Deletes the lines one audio source produced, before re-transcribing it. Lines with
        no source are never touched: they were imported, or predate source tracking.
        """
        await self.session.execute(
            sa_delete(DBTranscriptLine).where(DBTranscriptLine.source_id == str(source_id))
        )

    async def search(self, query: str, limit: int = SEARCH_LIMIT) -> list[TranscriptLine]:
        """
        Lines containing every word of `query`, in transcript order, through the
        `transcript_search` FTS5 index. Matching ignores case and accents. See
        docs/search.md.
        """
        match = fts_query(query)
        if match is None:
            return []
        matching = text(
            "SELECT rowid FROM transcript_search WHERE transcript_search MATCH :match"
        ).bindparams(match=match)
        result = await self.session.execute(
            select(DBTranscriptLine)
            .where(literal_column("transcript_lines.rowid").in_(matching))
            .order_by(DBTranscriptLine.start_time)
            .limit(limit)
        )
        return self._to_lines(result.scalars().all())
