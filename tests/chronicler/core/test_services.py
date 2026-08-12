from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from chronicler.core.processing.regex_guard import UnsafePatternError
from chronicler.core.repositories import ChronicleRepository, TaskRepository
from chronicler.core.services.chronicle_service import ChronicleService
from chronicler.core.services.task_service import TaskService


@pytest.mark.asyncio
async def test_list_chronicles():
    repo = MagicMock(spec=ChronicleRepository)
    repo.get_all = AsyncMock(return_value=[])

    service = ChronicleService(repo)
    result = await service.list_chronicles()

    assert result == []
    repo.get_all.assert_called_once()


@pytest.mark.asyncio
async def test_create_chronicle():
    repo = MagicMock(spec=ChronicleRepository)
    repo.create = AsyncMock(side_effect=lambda x: x)

    service = ChronicleService(repo)
    result = await service.create_chronicle("New Chronicle")

    assert result.title == "New Chronicle"
    repo.create.assert_called_once()


@pytest.mark.asyncio
async def test_search_chronicles():
    repo = MagicMock(spec=ChronicleRepository)
    repo.search = AsyncMock(return_value=[])

    service = ChronicleService(repo)
    await service.search_chronicles("test")

    repo.search.assert_called_once_with("test")


@pytest.mark.asyncio
async def test_search_tasks():
    repo = MagicMock(spec=TaskRepository)
    repo.search = AsyncMock(return_value=[])

    service = TaskService(repo)
    await service.search_tasks("test")

    repo.search.assert_called_once_with("test")


@pytest.mark.asyncio
async def test_queue_import_rejects_catastrophic_regex():
    repo = MagicMock(spec=TaskRepository)
    repo.create = AsyncMock(side_effect=lambda x: x)

    service = TaskService(repo)

    with pytest.raises(UnsafePatternError):
        await service.queue_import(
            chronicle_id=uuid4(), file_path="/imports/x.txt", regex=r"(a+)+$"
        )

    # No task should have been created for a rejected pattern.
    repo.create.assert_not_called()


@pytest.mark.asyncio
async def test_queue_import_accepts_safe_regex():
    repo = MagicMock(spec=TaskRepository)
    repo.create = AsyncMock(side_effect=lambda x: x)

    service = TaskService(repo)
    task = await service.queue_import(
        chronicle_id=uuid4(), file_path="/imports/x.txt", regex=r"^([A-Za-z]+):\s*(.*)$"
    )

    repo.create.assert_called_once()
    assert task is not None
