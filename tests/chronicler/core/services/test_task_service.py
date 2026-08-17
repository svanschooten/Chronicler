import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from chronicler.core.models import TaskStatus, TaskType
from chronicler.core.processing.regex_guard import UnsafePatternError
from chronicler.core.repositories import TaskRepository
from chronicler.core.services.task_service import TaskService


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


@pytest.mark.asyncio
async def test_queue_import_records_timestamp_group_when_given():
    repo = MagicMock(spec=TaskRepository)
    repo.create = AsyncMock(side_effect=lambda x: x)

    service = TaskService(repo)
    task = await service.queue_import(
        chronicle_id=uuid4(),
        file_path="/imports/x.txt",
        regex=r"^\[(\d\d:\d\d:\d\d)\] ([A-Za-z]+):\s*(.*)$",
        speaker_group=2,
        text_group=3,
        timestamp_group=1,
    )

    assert json.loads(task.data)["timestamp_group"] == 1


@pytest.mark.asyncio
async def test_queue_import_omits_timestamp_group_by_default():
    repo = MagicMock(spec=TaskRepository)
    repo.create = AsyncMock(side_effect=lambda x: x)

    service = TaskService(repo)
    task = await service.queue_import(
        chronicle_id=uuid4(), file_path="/imports/x.txt", regex=r"^([A-Za-z]+):\s*(.*)$"
    )

    assert "timestamp_group" not in json.loads(task.data)


@pytest.mark.asyncio
async def test_queue_import_defaults_to_not_appending():
    repo = MagicMock(spec=TaskRepository)
    repo.create = AsyncMock(side_effect=lambda x: x)

    service = TaskService(repo)
    task = await service.queue_import(chronicle_id=uuid4(), file_path="/imports/x.txt")

    assert "append" not in json.loads(task.data)


@pytest.mark.asyncio
async def test_queue_import_append_true_is_recorded_in_task_data():
    repo = MagicMock(spec=TaskRepository)
    repo.create = AsyncMock(side_effect=lambda x: x)

    service = TaskService(repo)
    task = await service.queue_import(
        chronicle_id=uuid4(), file_path="/imports/x.txt", append=True
    )

    assert json.loads(task.data)["append"] is True


@pytest.mark.asyncio
async def test_retry_task_puts_it_back_on_the_queue():
    repo = MagicMock(spec=TaskRepository)
    repo.update_status = AsyncMock()
    task_id = uuid4()

    await TaskService(repo).retry_task(task_id)

    repo.update_status.assert_awaited_once_with(task_id, TaskStatus.PENDING)


@pytest.mark.asyncio
async def test_queue_transcribe_creates_transcribe_task():
    repo = MagicMock(spec=TaskRepository)
    repo.create = AsyncMock(side_effect=lambda x: x)

    service = TaskService(repo)
    task = await service.queue_transcribe(
        chronicle_id=uuid4(), file_path="/imports/audio.mp3", speaker_name="Alice"
    )

    assert task.type == TaskType.TRANSCRIBE
    assert json.loads(task.data)["file_path"] == "/imports/audio.mp3"
    assert json.loads(task.data)["speaker_name"] == "Alice"
