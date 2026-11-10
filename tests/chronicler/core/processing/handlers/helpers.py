"""Shared helpers for the handler tests."""

from uuid import UUID

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import Chronicle
from chronicler.core.sqlite import SQLiteChronicleRepository


async def read_chronicle(db_manager: DatabaseManager, chronicle_id: UUID) -> Chronicle:
    """A chronicle as a fresh session sees it, so a test cannot pass on a cached row."""
    async with db_manager.get_archive_session() as session:
        chronicle = await SQLiteChronicleRepository(session).get_by_id(chronicle_id)
    assert chronicle is not None
    return chronicle
