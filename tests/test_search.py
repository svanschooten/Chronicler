from unittest.mock import AsyncMock, MagicMock

import pytest

from chronicler.core.repositories import ChronicleRepository, TaskRepository
from chronicler.core.services.chronicle_service import ChronicleService
from chronicler.core.services.task_service import TaskService


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
