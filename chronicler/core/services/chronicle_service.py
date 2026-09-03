import logging
import shutil
from pathlib import Path
from uuid import UUID

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.file_staging import confine_to_directory, safe_display_name
from chronicler.core.models import Chronicle
from chronicler.core.repositories import ChronicleRepository
from chronicler.core.rpc import service

logger = logging.getLogger(__name__)


@service
class ChronicleService:
    def __init__(self, repository: ChronicleRepository, db_manager: DatabaseManager):
        self.repository = repository
        self.db_manager = db_manager

    async def list_chronicles(self) -> list[Chronicle]:
        return await self.repository.get_all()

    async def get_chronicle(self, chronicle_id: UUID) -> Chronicle | None:
        return await self.repository.get_by_id(chronicle_id)

    async def create_chronicle(
        self, title: str, project_path: str | None = None, source_file: str | None = None
    ) -> Chronicle:
        chronicle = Chronicle(title=title, project_path=project_path, source_file=source_file)
        return await self.repository.create(chronicle)

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
        sources_dir = self.db_manager.get_chronicle_sources_path(str(chronicle_id))
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
