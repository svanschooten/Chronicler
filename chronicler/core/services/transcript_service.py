from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import TranscriptLine
from chronicler.core.repositories import ChronicleRepository
from chronicler.core.rpc import service
from chronicler.core.sqlite import SQLiteTranscriptRepository


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
