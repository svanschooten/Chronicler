"""Adding and removing a chronicle's tags through the service layer."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import Chronicle
from chronicler.core.services.chronicle_service import ChronicleService
from chronicler.core.sqlite import SQLiteChronicleRepository


@pytest_asyncio.fixture
async def archive(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    session = db_manager.get_archive_session()
    repository = SQLiteChronicleRepository(session)
    chronicle = await repository.create(Chronicle(title="Session"))
    yield ChronicleService(repository, db_manager, AsyncMock()), chronicle
    await session.close()
    await db_manager.close_all()


def _names(chronicle):
    return [tag.name for tag in chronicle.tags]


@pytest.mark.asyncio
async def test_a_tag_is_added_and_returned_with_the_chronicle(archive):
    service, chronicle = archive

    tagged = await service.add_tag(chronicle.id, "  Campaign   notes ")

    assert _names(tagged) == ["Campaign notes"]


@pytest.mark.asyncio
async def test_a_blank_tag_changes_nothing(archive):
    service, chronicle = archive

    assert _names(await service.add_tag(chronicle.id, "   ")) == []


@pytest.mark.asyncio
async def test_removing_the_last_use_of_a_tag_deletes_it(archive):
    service, chronicle = archive
    await service.add_tag(chronicle.id, "product")

    untagged = await service.remove_tag(chronicle.id, "product")

    assert _names(untagged) == []
    again = await service.add_tag(chronicle.id, "Product")
    assert _names(again) == ["Product"]  # the old spelling did not linger


@pytest.mark.asyncio
async def test_tags_of_an_unknown_chronicle_are_refused(archive):
    service, _ = archive

    with pytest.raises(LookupError):
        await service.add_tag(uuid4(), "x")
    with pytest.raises(LookupError):
        await service.remove_tag(uuid4(), "x")


@pytest.mark.asyncio
@pytest.mark.parametrize("again", ["Über", "über", "ÜBER"])
async def test_a_tag_with_a_non_ascii_capital_is_reused(archive, again):
    """SQLite's lower() folds ASCII only, which made "Über" miss itself."""
    service, chronicle = archive
    other = await service.repository.create(Chronicle(title="Other"))
    await service.add_tag(chronicle.id, "Über")

    tagged = await service.add_tag(other.id, again)

    assert _names(tagged) == ["Über"]


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["Transcript", "summarized"])
async def test_a_system_tag_cannot_be_removed(archive, name):
    service, chronicle = archive
    await service.repository.add_tag(chronicle.id, "Transcript")
    await service.repository.add_tag(chronicle.id, "Summarized")

    with pytest.raises(ValueError):
        await service.remove_tag(chronicle.id, name)

    assert sorted(_names(await service.get_chronicle(chronicle.id))) == [
        "Summarized",
        "Transcript",
    ]
