import asyncio
import logging
import tempfile
import textwrap
from pathlib import Path
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.database_manager import DatabaseManager, NewerSchemaError
from chronicler.core.formatting import format_timestamp
from chronicler.core.models import AudioSource, Chronicle, Summary, TranscriptLine, TranscriptMatch
from chronicler.core.processing.fingerprint import fingerprint_file
from chronicler.core.repositories import ChronicleRepository, KnownSpeakerRepository
from chronicler.core.rpc import service
from chronicler.core.services.bundle import (
    DATABASE_NAME,
    BundleManifest,
    format_bundle,
    safe_folder_name,
)
from chronicler.core.services.html import format_html
from chronicler.core.services.srt import format_srt
from chronicler.core.sqlite import (
    SQLiteAudioSourceRepository,
    SQLiteSummaryRepository,
    SQLiteTranscriptRepository,
)
from chronicler.core.sqlite.transcript_repository import SEARCH_LIMIT

logger = logging.getLogger(__name__)

PLAINTEXT_EXPORT_WIDTH = 140
# Lines shown per chronicle in a workspace search, and chronicles searched at once.
MATCHES_PER_CHRONICLE = 3
SEARCH_CONCURRENCY = 8
# Lines a chronicle's own find returns at most.
FIND_LIMIT = SEARCH_LIMIT
NORMALIZED_SUFFIX = ".normalized.wav"


@service(
    expose=[
        "assign_speaker",
        "delete_summary",
        "export_html",
        "export_pdf",
        "export_plaintext",
        "delete_line",
        "export_srt",
        "export_zip",
        "get_transcript",
        "list_audio_sources",
        "list_summaries",
        "read_transcript_text",
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
        chronicle_repository: ChronicleRepository,
        known_speakers: KnownSpeakerRepository | None = None,
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

        if speaker_name:
            await self._remember_speaker(speaker_name)
        return line

    async def delete_line(self, chronicle_id: UUID, line_id: UUID) -> None:
        """Removes one line. The speaker row stays - it still names an audio source."""
        async with self.db_manager.transaction(chronicle_id) as session:
            await SQLiteTranscriptRepository(session).delete_line(line_id)

    async def export_plaintext(self, chronicle_id: UUID, include_timestamps: bool = False) -> str:
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

    async def sources_dir(self, chronicle_id: UUID) -> Path:
        """Beside a linked project.db, otherwise in the workspace - see docs/audio-sources.md."""
        return self.db_manager.sources_path_for(
            str(chronicle_id), await self.db_manager.project_path_for(chronicle_id)
        )

    async def source_path(self, chronicle_id: UUID, filename: str) -> Path:
        return (await self.sources_dir(chronicle_id)) / filename

    async def _source_files(self, chronicle_id: UUID) -> list[Path]:
        directory = await self.sources_dir(chronicle_id)
        return list(directory.iterdir()) if directory.is_dir() else []

    async def _on_disk(self, chronicle_id: UUID) -> list[Path]:
        return sorted(
            path
            for path in await self._source_files(chronicle_id)
            if path.is_file() and not path.name.endswith(NORMALIZED_SUFFIX)
        )

    async def export_srt(self, chronicle_id: UUID, include_speaker: bool = True) -> str:
        """Subtitles for a transcribed chronicle, refusing text imports that have no timings."""
        lines = await self.get_transcript(chronicle_id)
        return format_srt(lines, include_speaker=include_speaker, require_real_timestamps=True)

    async def export_html(self, chronicle_id: UUID, chronicle_title: str) -> str:
        """HTML for a transcribed chronicle."""
        lines = await self.get_transcript(chronicle_id)
        return format_html(lines, chronicle_title)

    async def export_pdf(self, chronicle_id: UUID, chronicle_title: str) -> bytearray:
        """
        PDF for a transcribed chronicle.

        Laid out on a worker thread: a long transcript takes seconds, and the event loop
        this runs on is also the desktop UI's, or the server's for every other client.
        """
        # Imported here: fpdf costs about half a second and few sessions export a PDF.
        from chronicler.core.services.pdf import format_pdf

        lines = await self.get_transcript(chronicle_id)
        return await asyncio.to_thread(format_pdf, lines, chronicle_title)

    async def export_zip(self, chronicle_id: UUID, include_sources: bool = False) -> bytearray:
        """
        A portable copy of the chronicle: its own database, plus a manifest naming what
        the workspace database knows and optionally the audio it was built from.

        Audio is opt-in because it dwarfs everything else - a bundle without it is a few
        hundred kilobytes, one with it is however many hours of recording. Left out, the
        sources are still listed in the manifest and their rows still exist, so they read
        as missing rather than as never having been there.
        """
        chronicle = await self.chronicle_repository.get_by_id(chronicle_id)
        if chronicle is None:
            raise LookupError(f"There is no chronicle {chronicle_id} to export")

        on_disk = await self._on_disk(chronicle_id)
        manifest = BundleManifest.of(
            chronicle, [path.name for path in on_disk], sources_included=include_sources
        )

        with tempfile.TemporaryDirectory() as workspace:
            snapshot = await self.db_manager.snapshot_project(
                str(chronicle_id),
                Path(workspace) / DATABASE_NAME,
            )
            # Off the event loop, like the PDF: with audio this compresses for seconds.
            return await asyncio.to_thread(
                format_bundle,
                snapshot,
                manifest,
                root=safe_folder_name(chronicle.title),
                sources=on_disk if include_sources else (),
            )

    async def list_summaries(self, chronicle_id: UUID) -> list[Summary]:
        """Every generated summary, numbered in the order they were produced."""
        async with await self._project_session(chronicle_id) as session:
            return await SQLiteSummaryRepository(session).list_summaries()

    async def delete_summary(self, chronicle_id: UUID, summary_id: UUID) -> None:
        async with self.db_manager.transaction(chronicle_id) as session:
            await SQLiteSummaryRepository(session).delete(summary_id)

    async def read_transcript_text(
        self, chronicle_id: UUID, include_timestamps: bool = False
    ) -> str:
        """The transcript as one readable block, for reading rather than editing."""
        return await self.export_plaintext(chronicle_id, include_timestamps=include_timestamps)

    async def chronicle_directory(self, chronicle_id: UUID) -> str:
        """
        Where this chronicle's files live, so a local client can offer to open it. Not
        exposed over RPC: on a thin client the path would be the server's.
        """
        project_path = await self.db_manager.project_path_for(chronicle_id)
        if project_path:
            return str(project_path.parent)
        return str(self.db_manager.workspace_path / "chronicles" / str(chronicle_id))

    async def list_audio_sources(self, chronicle_id: UUID) -> list[AudioSource]:
        """This chronicle's tracks, reconciling what is on disk with the recorded state."""
        async with self.db_manager.transaction(chronicle_id) as session:
            repo = SQLiteAudioSourceRepository(session)
            present = set()
            for path in await self._on_disk(chronicle_id):
                present.add(path.name)
                await repo.register(
                    path.name,
                    content_hash=fingerprint_file(path),
                    size_bytes=path.stat().st_size,
                )
            sources = await repo.list_sources()

        for source in sources:
            source.missing = source.filename not in present
            source.path = str(await self.source_path(chronicle_id, source.filename))
        return sources

    async def assign_speaker(
        self, chronicle_id: UUID, filename: str, speaker_name: str | None
    ) -> AudioSource | None:
        """Remembers which speaker a track belongs to, creating the speaker if needed."""
        async with self.db_manager.transaction(chronicle_id) as session:
            transcripts = SQLiteTranscriptRepository(session)
            sources = SQLiteAudioSourceRepository(session)
            speaker_id = None
            if speaker_name:
                speaker_id = (await transcripts.get_or_create_speaker(speaker_name)).id
            await sources.set_speaker(filename, speaker_id)
            source = await sources.get_by_filename(filename)

        if speaker_name:
            await self._remember_speaker(speaker_name)
        return source

    async def _remember_speaker(self, name: str) -> None:
        """Adds a name to the workspace-wide registry, ignoring a registry-side failure."""
        if self.known_speakers is None:
            return
        try:
            await self.known_speakers.register(name)
        except Exception:
            logger.warning("Could not record speaker %r in the workspace registry", name)

    async def list_known_speakers(self) -> list[str]:
        """Every speaker name seen anywhere in this workspace, not just this chronicle."""
        if self.known_speakers is None:
            return []
        return await self.known_speakers.list_names()

    async def speaker_suggestions(self, chronicle_id: UUID) -> list[str]:
        """Workspace-wide names first-class, with this chronicle's own folded in."""
        names = set(await self.list_known_speakers())
        names.update(await self.list_speaker_names(chronicle_id))
        return sorted(names, key=str.casefold)

    async def list_speaker_names(self, chronicle_id: UUID) -> list[str]:
        async with await self._project_session(chronicle_id) as session:
            speakers = await SQLiteTranscriptRepository(session).get_speakers()
        return sorted(speaker.name for speaker in speakers)

    async def refresh_speaker_count(self, chronicle_id: UUID) -> int:
        """
        Recompute Chronicle.speakers_count from the project db's speakers table - a
        manual reconciliation action for chronicles imported before this existed, or
        whose transcript was hand-edited since.
        """
        async with await self._project_session(chronicle_id) as session:
            speakers = await SQLiteTranscriptRepository(session).get_speakers()
        count = len(speakers)

        for speaker in speakers:
            await self._remember_speaker(speaker.name)

        chronicle = await self.chronicle_repository.get_by_id(chronicle_id)
        if chronicle and chronicle.speakers_count != count:
            chronicle.speakers_count = count
            await self.chronicle_repository.update(chronicle)
        return count
