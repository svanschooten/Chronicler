import logging
from uuid import UUID

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import Summary
from chronicler.core.rpc import service
from chronicler.core.sqlite import SQLiteSummaryRepository

logger = logging.getLogger(__name__)


@service(expose=["delete_summary", "list_summaries"])
class SummaryService:
    """A chronicle's generated summaries. Generating one is a SUMMARIZE task."""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    async def list_summaries(self, chronicle_id: UUID) -> list[Summary]:
        """Every generated summary, numbered in the order they were produced."""
        async with await self.db_manager.get_project_session(
            chronicle_id, must_exist=True
        ) as session:
            return await SQLiteSummaryRepository(session).list_summaries()

    async def delete_summary(self, chronicle_id: UUID, summary_id: UUID) -> None:
        async with self.db_manager.transaction(chronicle_id) as session:
            await SQLiteSummaryRepository(session).delete(summary_id)
