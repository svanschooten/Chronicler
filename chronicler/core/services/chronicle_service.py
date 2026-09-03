import logging
import shutil
from pathlib import Path
from uuid import UUID

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.file_staging import confine_to_directory, safe_display_name
from chronicler.core.formatting import format_duration
from chronicler.core.models import Chronicle
from chronicler.core.repositories import ChronicleRepository
from chronicler.core.rpc import service
from chronicler.core.services.transcript_service import TranscriptService

logger = logging.getLogger(__name__)


@service(
    expose=[
        "add_audio_source",
        "create_chronicle",
        "delete_chronicle",
        "get_chronicle",
        "link_external_chronicle",
        "list_chronicles",
        "search_chronicles",
        "update_chronicle",
    ]
)
class ChronicleService:
    def __init__(
        self,
        repository: ChronicleRepository,
        db_manager: DatabaseManager,
        transcripts: TranscriptService | None = None,
    ):
        self.repository = repository
        self.db_manager = db_manager
        self.transcripts = transcripts

    async def list_chronicles(self) -> list[Chronicle]:
        return await self.repository.get_all()

    async def get_chronicle(self, chronicle_id: UUID) -> Chronicle | None:
        return await self.repository.get_by_id(chronicle_id)

    async def create_chronicle(
        self, title: str, project_path: str | None = None, source_file: str | None = None
    ) -> Chronicle:
        chronicle = Chronicle(title=title, project_path=project_path, source_file=source_file)
        return await self.repository.create(chronicle)

    async def link_external_chronicle(self, project_path: str) -> Chronicle:
        """
        Registers a project.db that lives outside the workspace, and reads what it can
        out of it.

        One service call rather than create-then-inspect from the client: a thin client
        would otherwise make four round trips, and a half-registered chronicle showing
        "Imported" with no speakers is the state this replaces. See docs/storage.md.
        """
        path = Path(project_path)
        chronicle = await self.create_chronicle(_title_for(path), project_path=str(path))
        return await self.hydrate_from_project(chronicle.id)

    async def hydrate_from_project(self, chronicle_id: UUID) -> Chronicle:
        """Fills in speaker count, duration and status from what the project db holds."""
        chronicle = await self.repository.get_by_id(chronicle_id)
        if chronicle is None:
            raise ValueError(f"No chronicle {chronicle_id}")
        if self.transcripts is None:
            return chronicle

        speakers = await self.transcripts.refresh_speaker_count(chronicle_id)
        lines = await self.transcripts.get_transcript(chronicle_id)

        if lines:
            await self.repository.add_tag(chronicle_id, "Transcript")

        chronicle = await self.repository.get_by_id(chronicle_id) or chronicle
        chronicle.speakers_count = speakers
        if lines:
            chronicle.duration = format_duration(max(line.end_time for line in lines))
            chronicle.status = "Transcribed"
        logger.info(f"Hydrated chronicle {chronicle_id}: {speakers} speakers, {len(lines)} lines")
        return await self.repository.update(chronicle)

    async def update_chronicle(self, chronicle: Chronicle) -> Chronicle:
        return await self.repository.update(chronicle)

    async def delete_chronicle(self, chronicle_id: UUID) -> None:
        chronicle = await self.repository.get_by_id(chronicle_id)
        await self.repository.delete(chronicle_id)

        if chronicle and not chronicle.project_path:
            chronicle_dir = self.db_manager.workspace_path / "chronicles" / str(chronicle_id)
            if chronicle_dir.exists():
                shutil.rmtree(chronicle_dir)
                logger.info(f"Removed chronicle directory {chronicle_dir}")

    async def search_chronicles(self, query: str) -> list[Chronicle]:
        return await self.repository.search(query)

    async def add_audio_source(
        self, chronicle_id: UUID, file_path: str, original_name: str | None = None
    ) -> str:
        """
        Moves a staged file (see file_staging.py - staged under a throwaway UUID name,
        not the original one) into the chronicle's durable sources/ directory under its
        *original* name, so a later "which track is this?" listing (see
        TranscriptService.list_audio_sources) is actually readable.
        """
        chronicle = await self.repository.get_by_id(chronicle_id)
        sources_dir = self.db_manager.sources_path_for(
            str(chronicle_id),
            Path(chronicle.project_path) if chronicle and chronicle.project_path else None,
        )
        resolved_source = confine_to_directory(
            file_path, self.db_manager.get_imports_path(), "the imports directory"
        )
        name = safe_display_name(original_name or resolved_source.name, resolved_source.name)
        stem, suffix = Path(name).stem, Path(name).suffix
        dest = sources_dir / name
        counter = 1
        while dest.exists():
            dest = sources_dir / f"{stem} ({counter}){suffix}"
            counter += 1

        shutil.move(resolved_source, dest)
        logger.info(f"Added audio source '{dest.name}' for chronicle {chronicle_id}")
        return str(dest)


def _title_for(project_path: Path) -> str:
    """A linked chronicle is named after its own folder, not after "project.db"."""
    title = project_path.parent.name
    if title in ("", "chronicles"):
        return project_path.stem
    return title
