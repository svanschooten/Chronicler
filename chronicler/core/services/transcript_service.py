import textwrap
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.formatting import format_timestamp
from chronicler.core.models import TranscriptLine
from chronicler.core.repositories import ChronicleRepository
from chronicler.core.rpc import service
from chronicler.core.sqlite import SQLiteTranscriptRepository

PLAINTEXT_EXPORT_WIDTH = 140


@service
class TranscriptService:
    """Project-scoped, unlike every other service here: which project.db to read
    depends on chronicle_id, known only per-call, not at construction time. Opens its
    own project session per call instead of taking a pre-bound TranscriptRepository -
    the same pattern WorkerHandlers already uses in processing/handlers.py. This is
    what lets it be resolved the same way locally (Container) or remotely
    (RemoteContainer/RPC) as every other service: DatabaseManager is a singleton
    either way, and chronicle_id is just another request-body field.
    """

    def __init__(self, db_manager: DatabaseManager, chronicle_repository: ChronicleRepository):
        self.db_manager = db_manager
        self.chronicle_repository = chronicle_repository

    async def _get_repository(
        self, chronicle_id: UUID
    ) -> tuple[AsyncSession, SQLiteTranscriptRepository]:
        custom_path = None
        chronicle = await self.chronicle_repository.get_by_id(chronicle_id)
        if chronicle and chronicle.project_path:
            custom_path = Path(chronicle.project_path)

        session = await self.db_manager.get_project_session(
            str(chronicle_id), custom_path=custom_path
        )
        return session, SQLiteTranscriptRepository(session)

    async def get_transcript(self, chronicle_id: UUID) -> list[TranscriptLine]:
        session, repo = await self._get_repository(chronicle_id)
        async with session:
            return await repo.get_lines()

    async def update_line(self, chronicle_id: UUID, line: TranscriptLine) -> TranscriptLine:
        # Not implemented yet (Sprint 4 - see TODO.md "Edit text"). Still project-
        # scoped and chronicle_id-aware for API consistency with get_transcript, but
        # behavior is unchanged: returns the input without persisting.
        return line

    async def export_plaintext(self, chronicle_id: UUID, include_timestamps: bool = False) -> str:
        # Speaker names are padded to a fixed column (the longest name in this
        # transcript) so every colon lines up, matching examples/
        # example_transcript_001.txt's own convention. A turn's original line breaks
        # (RegexImporter joins them with "\n", not " " - see importers.py) are kept
        # as separate output lines rather than flattened into one paragraph; each of
        # those (and a Cleaned turn's single merged line, which has no "\n" of its
        # own) is still wrapped at PLAINTEXT_EXPORT_WIDTH if it's long enough to need
        # it, hanging-indented under the padded speaker column. Lines with no real
        # text (blank/whitespace only) are dropped rather than exported as a bare
        # "Speaker: ". include_timestamps prepends each line's "[HH:MM:SS] " (a fixed
        # width, unlike the speaker column) - same wrap/indent rules either way, just
        # a wider prefix to align continuation lines under.
        lines = [line for line in await self.get_transcript(chronicle_id) if line.text.strip()]
        if not lines:
            return ""

        speaker_width = max(len(line.speaker_name or "Unknown") for line in lines)

        formatted = []
        for line in lines:
            speaker_label = f"{(line.speaker_name or 'Unknown'):<{speaker_width}}: "
            prefix = (
                f"[{format_timestamp(line.start_time)}] {speaker_label}"
                if include_timestamps
                else speaker_label
            )
            continuation_indent = " " * len(prefix)
            sub_lines = [s for s in (part.strip() for part in line.text.split("\n")) if s]
            for i, sub_line in enumerate(sub_lines):
                formatted.append(
                    textwrap.fill(
                        sub_line,
                        width=PLAINTEXT_EXPORT_WIDTH,
                        initial_indent=prefix if i == 0 else continuation_indent,
                        subsequent_indent=continuation_indent,
                    )
                )
        return "\n".join(formatted)

    async def list_audio_sources(self, chronicle_id: UUID) -> list[str]:
        """Full paths (not just filenames) - the caller needs one back verbatim to
        pass to TaskService.queue_transcribe, and this runs server-side even in thin
        client mode (see rpc.py - only coroutine functions are remotable, which is
        also why this is async despite being plain filesystem I/O), so the path is
        always meaningful on whichever machine will actually read it. The
        sources/ directory itself is the source of truth for "what audio tracks does
        this chronicle have" (see ChronicleService.add_audio_source) - no DB table
        needed for that yet.
        """
        sources_dir = self.db_manager.get_chronicle_sources_path(str(chronicle_id))
        return sorted(str(p) for p in sources_dir.iterdir() if p.is_file())

    async def list_speaker_names(self, chronicle_id: UUID) -> list[str]:
        session, repo = await self._get_repository(chronicle_id)
        async with session:
            return sorted(speaker.name for speaker in await repo.get_speakers())

    async def refresh_speaker_count(self, chronicle_id: UUID) -> int:
        """Recompute Chronicle.speakers_count from the project db's speakers table -
        a manual reconciliation action for chronicles imported before this existed, or
        whose transcript was hand-edited since. Import/clean already backfill this
        automatically as a side effect (see WorkerHandlers), so this is only needed
        as an explicit "Identify Speakers" user action, not on every load.
        """
        session, repo = await self._get_repository(chronicle_id)
        async with session:
            count = len(await repo.get_speakers())

        chronicle = await self.chronicle_repository.get_by_id(chronicle_id)
        if chronicle and chronicle.speakers_count != count:
            chronicle.speakers_count = count
            await self.chronicle_repository.update(chronicle)
        return count
