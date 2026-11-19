import asyncio
import logging
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.database_manager import DatabaseManager, NewerSchemaError
from chronicler.core.models import (
    Chronicle,
    TranscriptLine,
    TranscriptMatch,
)
from chronicler.core.reconcile import reconcile, update_speaker_count
from chronicler.core.rpc import service
from chronicler.core.services.speakers import remember_speaker
from chronicler.core.sqlite import (
    SQLiteChronicleRepository,
    SQLiteKnownSpeakerRepository,
    SQLiteTranscriptRepository,
)
from chronicler.core.sqlite.known_speaker_repository import normalize_speaker_name
from chronicler.core.sqlite.transcript_repository import SEARCH_LIMIT

logger = logging.getLogger(__name__)

# Lines shown per chronicle in a workspace search, and chronicles searched at once.
MATCHES_PER_CHRONICLE = 3
SEARCH_CONCURRENCY = 8
# Lines a chronicle's own find returns at most.
FIND_LIMIT = SEARCH_LIMIT


@service(
    expose=[
        "delete_line",
        "get_transcript",
        "refresh_speaker_count",
        "search_transcript",
        "search_transcripts",
        "speaker_suggestions",
        "update_line",
    ]
)
class TranscriptService:
    """
    Project-scoped, unlike every other service here: which project.db to read depends on
    chronicle_id, known only per-call, not at construction time.
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        chronicle_repository: SQLiteChronicleRepository,
        known_speakers: SQLiteKnownSpeakerRepository | None = None,
    ):
        self.db_manager = db_manager
        self.chronicle_repository = chronicle_repository
        self.known_speakers = known_speakers

    async def _project_session(self, chronicle_id: UUID) -> AsyncSession:
        """A session on the chronicle's database. Raises for an unknown or moved one."""
        return await self.db_manager.get_project_session(chronicle_id, must_exist=True)

    async def get_transcript(self, chronicle_id: UUID) -> list[TranscriptLine]:
        async with await self._project_session(chronicle_id) as session:
            return await SQLiteTranscriptRepository(session).get_lines()

    async def search_transcript(
        self, chronicle_id: UUID, query: str, limit: int = FIND_LIMIT
    ) -> list[TranscriptLine]:
        """
        This chronicle's lines containing every word of `query`, at most `limit` of them
        (no more than `FIND_LIMIT + 1`, so a caller can ask for one extra to tell whether
        there are more). See docs/search.md.
        """
        limit = max(1, min(limit, FIND_LIMIT + 1))
        async with await self._project_session(chronicle_id) as session:
            return await SQLiteTranscriptRepository(session).search(query, limit=limit)

    async def search_transcripts(self, query: str) -> list[TranscriptMatch]:
        """
        Every chronicle whose transcript has a line containing every word of `query`, with
        its first few matching lines, newest chronicle first.

        A fan-out over each chronicle's own index rather than one workspace index, so there
        is nothing to keep in sync. A chronicle that cannot be opened (a linked file that
        moved, one a newer Chronicler upgraded) is skipped, not an error, and so is a
        linked one that opening would upgrade: its file may be shared with an older
        Chronicler. See docs/search.md.
        """
        if not query.strip():
            return []
        chronicles = await self.chronicle_repository.get_all()
        limit = asyncio.Semaphore(SEARCH_CONCURRENCY)

        async def search_one(chronicle: Chronicle) -> TranscriptMatch | None:
            async with limit:
                try:
                    if await self.db_manager.would_upgrade_linked(chronicle.id):
                        logger.info(
                            f"Skipped linked chronicle {chronicle.id} in search: opening it "
                            "would upgrade its file"
                        )
                        return None
                    async with await self._project_session(chronicle.id) as session:
                        lines = await SQLiteTranscriptRepository(session).search(
                            query, limit=MATCHES_PER_CHRONICLE + 1
                        )
                except (LookupError, OSError, NewerSchemaError, SQLAlchemyError) as error:
                    logger.warning(f"Skipped chronicle {chronicle.id} in search: {error}")
                    return None
            if not lines:
                return None
            return TranscriptMatch(
                chronicle=chronicle,
                lines=lines[:MATCHES_PER_CHRONICLE],
                has_more=len(lines) > MATCHES_PER_CHRONICLE,
            )

        found = await asyncio.gather(*(search_one(chronicle) for chronicle in chronicles))
        return [match for match in found if match is not None]

    async def update_line(
        self,
        chronicle_id: UUID,
        line_id: UUID,
        text: str | None = None,
        speaker_name: str | None = None,
    ) -> TranscriptLine:
        """
        Corrects one line's text, its speaker, or both.

        A speaker typed here is created if new and joins the workspace-wide registry, so
        a name learned while correcting a transcript is offered the next time a track is
        transcribed. See docs/transcript-editing.md.
        """
        async with self.db_manager.transaction(chronicle_id) as session:
            repo = SQLiteTranscriptRepository(session)
            speaker_id = None
            if speaker_name:
                speaker_id = (await repo.get_or_create_speaker(speaker_name)).id
            line = await repo.update_line(line_id, text=text, speaker_id=speaker_id)
            lines = await repo.get_lines()
        await update_speaker_count(self.chronicle_repository, chronicle_id, lines)

        if speaker_name and line.speaker_name:
            # The spelling the chronicle already uses, which may differ in case from what
            # was typed.
            await remember_speaker(self.known_speakers, line.speaker_name)
        return line

    async def delete_line(self, chronicle_id: UUID, line_id: UUID) -> None:
        """
        Removes one line. The speaker row stays - it still names an audio source - but a
        speaker left with no lines stops counting.
        """
        async with self.db_manager.transaction(chronicle_id) as session:
            repo = SQLiteTranscriptRepository(session)
            await repo.delete_line(line_id)
            lines = await repo.get_lines()
        await update_speaker_count(self.chronicle_repository, chronicle_id, lines)

    async def list_known_speakers(self) -> list[str]:
        """Every speaker name seen anywhere in this workspace, not just this chronicle."""
        if self.known_speakers is None:
            return []
        return await self.known_speakers.list_names()

    async def speaker_suggestions(self, chronicle_id: UUID) -> list[str]:
        """
        Workspace-wide names first-class, with this chronicle's own folded in. Names that
        differ only in case or spacing are offered once, in the registry's spelling.
        """
        names: dict[str, str] = {}
        for name in await self.list_known_speakers():
            names.setdefault(normalize_speaker_name(name), name)
        for name in await self.list_speaker_names(chronicle_id):
            names.setdefault(normalize_speaker_name(name), name)
        return sorted(names.values(), key=str.casefold)

    async def list_speaker_names(self, chronicle_id: UUID) -> list[str]:
        async with await self._project_session(chronicle_id) as session:
            speakers = await SQLiteTranscriptRepository(session).get_speakers()
        return sorted(speaker.name for speaker in speakers)

    async def refresh_speaker_count(self, chronicle_id: UUID) -> int:
        """
        Reconciles the chronicle's row with its transcript and returns the speaker count - a
        manual action for chronicles imported before this existed, or whose transcript was
        hand-edited since.
        """
        async with await self._project_session(chronicle_id) as session:
            repo = SQLiteTranscriptRepository(session)
            speakers = await repo.get_speakers()
            lines = await repo.get_lines()
        for speaker in speakers:
            await remember_speaker(self.known_speakers, speaker.name)
        chronicle = await reconcile(self.chronicle_repository, chronicle_id, lines)
        return chronicle.speakers_count if chronicle else len({line.speaker_name for line in lines})
