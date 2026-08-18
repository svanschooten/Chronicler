"""Tests for SQLiteChronicleRepository."""

from datetime import datetime

import pytest
from sqlalchemy import select

from chronicler.core.database import chronicle_tags
from chronicler.core.models import Chronicle, Task, TaskType
from chronicler.core.sqlite import (
    SQLiteChronicleRepository,
    SQLiteTagRepository,
    SQLiteTaskRepository,
)


@pytest.mark.asyncio
async def test_create_and_get_chronicle(async_session):
    repo = SQLiteChronicleRepository(async_session)
    chronicle = Chronicle(title="Test Chronicle")

    created = await repo.create(chronicle)
    assert created.id == chronicle.id
    assert created.title == "Test Chronicle"

    fetched = await repo.get_by_id(chronicle.id)
    assert fetched is not None
    assert fetched.id == chronicle.id
    assert fetched.title == "Test Chronicle"


@pytest.mark.asyncio
async def test_get_all_chronicles(async_session):
    repo = SQLiteChronicleRepository(async_session)
    await repo.create(Chronicle(title="C1"))
    await repo.create(Chronicle(title="C2"))

    all_chronicles = await repo.get_all()
    assert len(all_chronicles) == 2
    assert {c.title for c in all_chronicles} == {"C1", "C2"}


@pytest.mark.asyncio
async def test_get_all_orders_newest_first(async_session):
    """Without an ORDER BY this returned whatever order SQLite produced, so the archive
    list could reshuffle between two refreshes that changed nothing."""
    repo = SQLiteChronicleRepository(async_session)
    await repo.create(Chronicle(title="Older", created_at=datetime(2026, 1, 1)))
    await repo.create(Chronicle(title="Newer", created_at=datetime(2026, 6, 1)))
    await repo.create(Chronicle(title="Middle", created_at=datetime(2026, 3, 1)))

    assert [c.title for c in await repo.get_all()] == ["Newer", "Middle", "Older"]


@pytest.mark.asyncio
async def test_search_orders_newest_first(async_session):
    repo = SQLiteChronicleRepository(async_session)
    await repo.create(Chronicle(title="Sync older", created_at=datetime(2026, 1, 1)))
    await repo.create(Chronicle(title="Sync newer", created_at=datetime(2026, 6, 1)))

    assert [c.title for c in await repo.search("Sync")] == ["Sync newer", "Sync older"]


@pytest.mark.asyncio
async def test_update_chronicle(async_session):
    repo = SQLiteChronicleRepository(async_session)
    chronicle = await repo.create(Chronicle(title="Old Title"))

    chronicle.title = "New Title"
    updated = await repo.update(chronicle)
    assert updated.title == "New Title"

    fetched = await repo.get_by_id(chronicle.id)
    assert fetched.title == "New Title"


@pytest.mark.asyncio
async def test_add_tag_creates_tag_and_attaches_it(async_session):
    repo = SQLiteChronicleRepository(async_session)
    chronicle = await repo.create(Chronicle(title="Test Chronicle"))

    await repo.add_tag(chronicle.id, "Transcript")

    fetched = await repo.get_by_id(chronicle.id)
    assert [t.name for t in fetched.tags] == ["Transcript"]


@pytest.mark.asyncio
async def test_add_tag_reuses_existing_tag_by_name(async_session):
    repo = SQLiteChronicleRepository(async_session)
    c1 = await repo.create(Chronicle(title="C1"))
    c2 = await repo.create(Chronicle(title="C2"))

    await repo.add_tag(c1.id, "Transcript")
    await repo.add_tag(c2.id, "Transcript")

    tags = await SQLiteTagRepository(async_session).get_all()
    assert len(tags) == 1


@pytest.mark.asyncio
async def test_add_tag_is_idempotent(async_session):
    repo = SQLiteChronicleRepository(async_session)
    chronicle = await repo.create(Chronicle(title="Test Chronicle"))

    await repo.add_tag(chronicle.id, "Transcript")
    await repo.add_tag(chronicle.id, "Transcript")

    fetched = await repo.get_by_id(chronicle.id)
    assert [t.name for t in fetched.tags] == ["Transcript"]


@pytest.mark.asyncio
async def test_delete_chronicle(async_session):
    repo = SQLiteChronicleRepository(async_session)
    chronicle = await repo.create(Chronicle(title="To be deleted"))

    await repo.delete(chronicle.id)
    fetched = await repo.get_by_id(chronicle.id)
    assert fetched is None


@pytest.mark.asyncio
async def test_delete_chronicle_cascades_tasks_and_tags(async_session):
    """DBTask.chronicle_id and chronicle_tags have no ondelete=CASCADE at the schema
    level - deleting a chronicle must clean these up explicitly or they're orphaned
    forever (a Task row pointing at a chronicle_id that no longer exists, or a tag
    association nothing will ever read again)."""
    chronicle_repo = SQLiteChronicleRepository(async_session)
    task_repo = SQLiteTaskRepository(async_session)

    chronicle = await chronicle_repo.create(Chronicle(title="To be deleted"))
    await chronicle_repo.add_tag(chronicle.id, "Transcript")
    task = await task_repo.create(Task(type=TaskType.IMPORT, chronicle_id=chronicle.id))
    other_chronicle = await chronicle_repo.create(Chronicle(title="Untouched"))
    other_task = await task_repo.create(Task(type=TaskType.IMPORT, chronicle_id=other_chronicle.id))

    await chronicle_repo.delete(chronicle.id)

    assert await task_repo.get_by_id(task.id) is None
    assert await task_repo.get_by_id(other_task.id) is not None

    tags_result = await async_session.execute(
        select(chronicle_tags).where(chronicle_tags.c.chronicle_id == str(chronicle.id))
    )
    assert tags_result.first() is None


@pytest.mark.asyncio
async def test_search_chronicles(async_session):
    repo = SQLiteChronicleRepository(async_session)
    await repo.create(Chronicle(title="Meeting One"))
    await repo.create(Chronicle(title="Interview Two"))

    results = await repo.search("Meeting")
    assert len(results) == 1
    assert results[0].title == "Meeting One"

    results = await repo.search("One")
    assert len(results) == 1
    assert results[0].title == "Meeting One"

    results = await repo.search("Three")
    assert len(results) == 0


@pytest.mark.asyncio
async def test_search_matches_the_description(async_session):
    repo = SQLiteChronicleRepository(async_session)
    await repo.create(Chronicle(title="Weekly sync", description="Roadmap and release priorities"))
    await repo.create(Chronicle(title="Interview", description="Coastal childhood"))

    results = await repo.search("roadmap")

    assert [c.title for c in results] == ["Weekly sync"]


@pytest.mark.asyncio
async def test_search_matches_a_tag_name(async_session):
    """Tagging a chronicle "product" and then searching "product" found nothing before -
    search only looked at the title."""
    repo = SQLiteChronicleRepository(async_session)
    tagged = await repo.create(Chronicle(title="Weekly sync"))
    await repo.create(Chronicle(title="Interview"))
    await repo.add_tag(tagged.id, "product")

    results = await repo.search("product")

    assert [c.title for c in results] == ["Weekly sync"]


@pytest.mark.asyncio
async def test_search_returns_a_chronicle_once_even_with_two_matching_tags(async_session):
    """The tag match is a subquery rather than a join precisely so this can't duplicate."""
    repo = SQLiteChronicleRepository(async_session)
    chronicle = await repo.create(Chronicle(title="Weekly sync"))
    await repo.add_tag(chronicle.id, "product-roadmap")
    await repo.add_tag(chronicle.id, "product-launch")

    results = await repo.search("product")

    assert len(results) == 1


@pytest.mark.asyncio
async def test_search_treats_like_wildcards_as_literal_text(async_session):
    """A bare "%" used to match every chronicle."""
    repo = SQLiteChronicleRepository(async_session)
    await repo.create(Chronicle(title="Coverage at 100%"))
    await repo.create(Chronicle(title="Interview"))

    assert [c.title for c in await repo.search("%")] == ["Coverage at 100%"]
    assert [c.title for c in await repo.search("100%")] == ["Coverage at 100%"]
    assert await repo.search("_nterview") == []


@pytest.mark.asyncio
async def test_search_ignores_a_null_description(async_session):
    """`NULL LIKE ...` is NULL, not false - the OR must still match on title alone."""
    repo = SQLiteChronicleRepository(async_session)
    await repo.create(Chronicle(title="Weekly sync"))

    assert len(await repo.search("Weekly")) == 1


@pytest.mark.asyncio
async def test_chronicle_project_path(async_session):
    repo = SQLiteChronicleRepository(async_session)
    chronicle = Chronicle(title="External Project", project_path="/external/path/project.db")

    created = await repo.create(chronicle)
    assert created.project_path == "/external/path/project.db"

    fetched = await repo.get_by_id(chronicle.id)
    assert fetched.project_path == "/external/path/project.db"


@pytest.mark.asyncio
async def test_chronicle_source_file(async_session):
    repo = SQLiteChronicleRepository(async_session)
    chronicle = Chronicle(title="Audio File", source_file="/path/to/audio.mp3")

    created = await repo.create(chronicle)
    assert created.source_file == "/path/to/audio.mp3"

    fetched = await repo.get_by_id(chronicle.id)
    assert fetched.source_file == "/path/to/audio.mp3"
