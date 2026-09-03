"""Tests for SearchService."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from chronicler.core.models import Chronicle, Tag, Task, TaskType
from chronicler.core.repositories import ChronicleRepository, TagRepository, TaskRepository
from chronicler.core.services.search_service import SearchService


def _service(chronicle_repo=None, tag_repo=None, task_repo=None) -> SearchService:
    return SearchService(
        task_repo or MagicMock(spec=TaskRepository),
        chronicle_repo or MagicMock(spec=ChronicleRepository),
        tag_repo or MagicMock(spec=TagRepository),
    )


@pytest.mark.asyncio
async def test_search_chronicle_meta_delegates_to_the_chronicle_repository():
    repo = MagicMock(spec=ChronicleRepository)
    repo.search = AsyncMock(return_value=[Chronicle(title="Weekly product sync")])

    result = await _service(chronicle_repo=repo).search_chronicle_meta("weekly")

    repo.search.assert_awaited_once_with("weekly")
    assert [c.title for c in result] == ["Weekly product sync"]


@pytest.mark.asyncio
async def test_search_tags_delegates_to_the_tag_repository():
    repo = MagicMock(spec=TagRepository)
    repo.search = AsyncMock(return_value=[Tag(name="product")])

    result = await _service(tag_repo=repo).search_tags("prod")

    repo.search.assert_awaited_once_with("prod")
    assert [t.name for t in result] == ["product"]


@pytest.mark.asyncio
async def test_search_tasks_delegates_to_the_task_repository():
    repo = MagicMock(spec=TaskRepository)
    repo.search = AsyncMock(return_value=[Task(type=TaskType.IMPORT)])

    result = await _service(task_repo=repo).search_tasks("import")

    repo.search.assert_awaited_once_with("import")
    assert len(result) == 1


@pytest.mark.parametrize("method", ["search_chronicle_content", "search_speakers"])
@pytest.mark.asyncio
async def test_per_project_searches_fail_loudly_rather_than_returning_nothing(method):
    """
    Transcript lines and speakers live in per-chronicle project databases, so these can't be
    a repository query against the archive - they need an FTS index or per-project fan-out
    first (TODO.md Phase 3).
    """
    with pytest.raises(NotImplementedError):
        await getattr(_service(), method)("anything")
