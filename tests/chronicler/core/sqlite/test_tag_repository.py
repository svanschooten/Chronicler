"""Tests for SQLiteTagRepository."""

import pytest

from chronicler.core.models import Tag
from chronicler.core.sqlite import (
    SQLiteTagRepository,
)


@pytest.mark.asyncio
async def test_create_and_get_all_tags(async_session):
    repo = SQLiteTagRepository(async_session)
    created = await repo.create(Tag(name="Important", color="#ff0000"))

    assert created.name == "Important"
    assert created.color == "#ff0000"

    all_tags = await repo.get_all()
    assert len(all_tags) == 1
    assert all_tags[0].id == created.id


@pytest.mark.asyncio
async def test_delete_tag(async_session):
    repo = SQLiteTagRepository(async_session)
    created = await repo.create(Tag(name="Temporary"))

    await repo.delete(created.id)

    all_tags = await repo.get_all()
    assert all_tags == []


@pytest.mark.asyncio
async def test_search_tags(async_session):
    repo = SQLiteTagRepository(async_session)
    await repo.create(Tag(name="D&D Session"))
    await repo.create(Tag(name="Interview"))

    results = await repo.search("D&D")
    assert len(results) == 1
    assert results[0].name == "D&D Session"

    results = await repo.search("interview")
    assert len(results) == 1
    assert results[0].name == "Interview"

    results = await repo.search("nonexistent")
    assert results == []
