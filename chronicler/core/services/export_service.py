import asyncio
import logging
import tempfile
from pathlib import Path
from uuid import UUID

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.exports.bundle import (
    DATABASE_NAME,
    BundleManifest,
    format_bundle,
    safe_folder_name,
)
from chronicler.core.exports.html import format_html
from chronicler.core.exports.plaintext import format_plaintext
from chronicler.core.exports.srt import format_srt
from chronicler.core.rpc import TempFile, service
from chronicler.core.services.source_service import SourceService
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.core.sqlite import SQLiteChronicleRepository

logger = logging.getLogger(__name__)


@service(expose=["export_html", "export_pdf", "export_plaintext", "export_srt", "export_zip"])
class ExportService:
    """A chronicle handed over as a file: text, subtitles, HTML, PDF or a portable zip."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        chronicle_repository: SQLiteChronicleRepository,
        transcripts: TranscriptService,
        sources: SourceService,
    ):
        self.db_manager = db_manager
        self.chronicle_repository = chronicle_repository
        self.transcripts = transcripts
        self.sources = sources

    async def export_plaintext(self, chronicle_id: UUID, include_timestamps: bool = False) -> str:
        """The transcript as one readable block, also what the viewer shows."""
        lines = await self.transcripts.get_transcript(chronicle_id)
        return format_plaintext(lines, include_timestamps)

    async def export_srt(self, chronicle_id: UUID, include_speaker: bool = True) -> str:
        """Subtitles for a transcribed chronicle, refusing text imports that have no timings."""
        lines = await self.transcripts.get_transcript(chronicle_id)
        return format_srt(lines, include_speaker=include_speaker, require_real_timestamps=True)

    async def export_html(self, chronicle_id: UUID, chronicle_title: str) -> str:
        """HTML for a transcribed chronicle."""
        lines = await self.transcripts.get_transcript(chronicle_id)
        return format_html(lines, chronicle_title)

    async def export_pdf(self, chronicle_id: UUID, chronicle_title: str) -> bytearray:
        """
        PDF for a transcribed chronicle.

        Laid out on a worker thread: a long transcript takes seconds, and the event loop
        this runs on is also the desktop UI's, or the server's for every other client.
        """
        # Imported here: fpdf costs about half a second and few sessions export a PDF.
        from chronicler.core.exports.pdf import format_pdf

        lines = await self.transcripts.get_transcript(chronicle_id)
        return await asyncio.to_thread(format_pdf, lines, chronicle_title)

    async def export_zip(self, chronicle_id: UUID, include_sources: bool = False) -> TempFile:
        """
        A portable copy of the chronicle: its own database, plus a manifest naming what
        the workspace database knows and optionally the audio it was built from.

        Audio is opt-in because it dwarfs everything else - a bundle without it is a few
        hundred kilobytes, one with it is however many hours of recording. Left out, the
        sources are still listed in the manifest and their rows still exist, so they read
        as missing rather than as never having been there.

        Returns a temporary file the caller owns and must move or delete: the archive is
        never held in memory. It is built in the workspace's exports folder, on the same disk
        as the audio, not in a system temporary directory that may be memory. Over RPC the
        server deletes its copy once it has been sent.
        """
        chronicle = await self.chronicle_repository.get_by_id(chronicle_id)
        if chronicle is None:
            raise LookupError(f"There is no chronicle {chronicle_id} to export")

        on_disk = await self.sources.on_disk(chronicle_id)
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
                directory=self.db_manager.get_exports_path(),
            )
