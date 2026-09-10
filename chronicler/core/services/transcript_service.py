import logging
import textwrap
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.formatting import format_timestamp
from chronicler.core.models import AudioSource, Summary, TranscriptLine
from chronicler.core.processing.fingerprint import fingerprint_file
from chronicler.core.repositories import ChronicleRepository, KnownSpeakerRepository
from chronicler.core.rpc import service
from chronicler.core.services.html import format_html
from chronicler.core.services.pdf import format_pdf
from chronicler.core.services.srt import format_srt
from chronicler.core.sqlite import (
    SQLiteAudioSourceRepository,
    SQLiteSummaryRepository,
    SQLiteTranscriptRepository,
)

logger = logging.getLogger(__name__)

PLAINTEXT_EXPORT_WIDTH = 140
NORMALIZED_SUFFIX = ".normalized.wav"


@service(
    expose=[
        "assign_speaker",
        "chronicle_directory",
        "delete_summary",
        "export_plaintext",
        "delete_line",
        "export_srt",
        "get_transcript",
        "list_audio_sources",
        "list_summaries",
        "read_transcript_text",
        "refresh_speaker_count",
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

    async def _get_repository(
        self, chronicle_id: UUID
    ) -> tuple[AsyncSession, SQLiteTranscriptRepository]:
        custom_path = await self._project_path(chronicle_id)
        session = await self.db_manager.get_project_session(
            str(chronicle_id), custom_path=custom_path
        )
        return session, SQLiteTranscriptRepository(session)

    async def _project_session(self, chronicle_id: UUID) -> AsyncSession:
        session, _ = await self._get_repository(chronicle_id)
        return session

    async def get_transcript(self, chronicle_id: UUID) -> list[TranscriptLine]:
        session, repo = await self._get_repository(chronicle_id)
        async with session:
            return await repo.get_lines()

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
        session, repo = await self._get_repository(chronicle_id)
        async with session:
            try:
                speaker_id = None
                if speaker_name:
                    speaker_id = (await repo.get_or_create_speaker(speaker_name)).id
                line = await repo.update_line(line_id, text=text, speaker_id=speaker_id)
                await session.commit()
            except Exception:
                await session.rollback()
                raise

        if speaker_name:
            await self._remember_speaker(speaker_name)
        return line

    async def delete_line(self, chronicle_id: UUID, line_id: UUID) -> None:
        """Removes one line. The speaker row stays - it still names an audio source."""
        session, repo = await self._get_repository(chronicle_id)
        async with session:
            try:
                await repo.delete_line(line_id)
                await session.commit()
            except Exception:
                await session.rollback()
                raise

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

    async def _project_path(self, chronicle_id: UUID) -> Path | None:
        chronicle = await self.chronicle_repository.get_by_id(chronicle_id)
        if chronicle and chronicle.project_path:
            return Path(chronicle.project_path)
        return None

    async def sources_dir(self, chronicle_id: UUID) -> Path:
        """Beside a linked project.db, otherwise in the workspace - see docs/audio-sources.md."""
        return self.db_manager.sources_path_for(
            str(chronicle_id), await self._project_path(chronicle_id)
        )

    async def source_path(self, chronicle_id: UUID, filename: str) -> Path:
        return (await self.sources_dir(chronicle_id)) / filename

    async def _on_disk(self, chronicle_id: UUID) -> list[Path]:
        return sorted(
            path
            for path in (await self.sources_dir(chronicle_id)).iterdir()
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
        """PDF for a transcribed chronicle."""
        lines = await self.get_transcript(chronicle_id)
        return format_pdf(lines, chronicle_title)

    async def list_summaries(self, chronicle_id: UUID) -> list[Summary]:
        """Every generated summary, numbered in the order they were produced."""
        session = await self._project_session(chronicle_id)
        async with session:
            return await SQLiteSummaryRepository(session).list_summaries()

    async def delete_summary(self, chronicle_id: UUID, summary_id: UUID) -> None:
        session = await self._project_session(chronicle_id)
        async with session:
            await SQLiteSummaryRepository(session).delete(summary_id)
            await session.commit()

    async def read_transcript_text(
        self, chronicle_id: UUID, include_timestamps: bool = False
    ) -> str:
        """The transcript as one readable block, for reading rather than editing."""
        return await self.export_plaintext(chronicle_id, include_timestamps=include_timestamps)

    async def chronicle_directory(self, chronicle_id: UUID) -> str:
        """Where this chronicle's files live, so a client can offer to open it."""
        chronicle = await self.chronicle_repository.get_by_id(chronicle_id)
        if chronicle and chronicle.project_path:
            return str(Path(chronicle.project_path).parent)
        return str(self.db_manager.workspace_path / "chronicles" / str(chronicle_id))

    async def list_audio_sources(self, chronicle_id: UUID) -> list[AudioSource]:
        """This chronicle's tracks, reconciling what is on disk with the recorded state."""
        session = await self._project_session(chronicle_id)
        async with session:
            repo = SQLiteAudioSourceRepository(session)
            present = set()
            for path in await self._on_disk(chronicle_id):
                present.add(path.name)
                await repo.register(
                    path.name,
                    content_hash=fingerprint_file(path),
                    size_bytes=path.stat().st_size,
                )
            await session.commit()
            sources = await repo.list_sources()

        for source in sources:
            source.missing = source.filename not in present
            source.path = str(await self.source_path(chronicle_id, source.filename))
        return sources

    async def assign_speaker(
        self, chronicle_id: UUID, filename: str, speaker_name: str | None
    ) -> AudioSource | None:
        """Remembers which speaker a track belongs to, creating the speaker if needed."""
        session = await self._project_session(chronicle_id)
        async with session:
            transcripts = SQLiteTranscriptRepository(session)
            sources = SQLiteAudioSourceRepository(session)
            try:
                speaker_id = None
                if speaker_name:
                    speaker_id = (await transcripts.get_or_create_speaker(speaker_name)).id
                await sources.set_speaker(filename, speaker_id)
                await session.commit()
                if speaker_name:
                    await self._remember_speaker(speaker_name)
            except Exception:
                await session.rollback()
                raise
            return await sources.get_by_filename(filename)

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
        session, repo = await self._get_repository(chronicle_id)
        async with session:
            return sorted(speaker.name for speaker in await repo.get_speakers())

    async def refresh_speaker_count(self, chronicle_id: UUID) -> int:
        """
        Recompute Chronicle.speakers_count from the project db's speakers table - a
        manual reconciliation action for chronicles imported before this existed, or
        whose transcript was hand-edited since.
        """
        session, repo = await self._get_repository(chronicle_id)
        async with session:
            speakers = await repo.get_speakers()
        count = len(speakers)

        for speaker in speakers:
            await self._remember_speaker(speaker.name)

        chronicle = await self.chronicle_repository.get_by_id(chronicle_id)
        if chronicle and chronicle.speakers_count != count:
            chronicle.speakers_count = count
            await self.chronicle_repository.update(chronicle)
        return count
