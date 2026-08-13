import json
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

    service = ChronicleService(repo, MagicMock())
    result = await service.list_chronicles()

    assert result == []
    repo.get_all.assert_called_once()


@pytest.mark.asyncio
async def test_create_chronicle():
    repo = MagicMock(spec=ChronicleRepository)
    repo.create = AsyncMock(side_effect=lambda x: x)

    service = ChronicleService(repo, MagicMock())
    result = await service.create_chronicle("New Chronicle")

    assert result.title == "New Chronicle"
    repo.create.assert_called_once()


@pytest.mark.asyncio
async def test_search_chronicles():
    repo = MagicMock(spec=ChronicleRepository)
    repo.search = AsyncMock(return_value=[])

    service = ChronicleService(repo, MagicMock())
    await service.search_chronicles("test")

    repo.search.assert_called_once_with("test")


@pytest.mark.asyncio
async def test_delete_chronicle_removes_directory_for_non_linked_chronicle(tmp_path):
    from chronicler.core.models import Chronicle

    chronicle_id = uuid4()
    chronicle_dir = tmp_path / "chronicles" / str(chronicle_id)
    chronicle_dir.mkdir(parents=True)
    (chronicle_dir / "project.db").write_text("data")

    repo = MagicMock(spec=ChronicleRepository)
    repo.get_by_id = AsyncMock(return_value=Chronicle(id=chronicle_id, title="Local"))
    repo.delete = AsyncMock()
    db_manager = MagicMock(workspace_path=tmp_path)

    service = ChronicleService(repo, db_manager)
    await service.delete_chronicle(chronicle_id)

    repo.delete.assert_awaited_once_with(chronicle_id)
    assert not chronicle_dir.exists()


@pytest.mark.asyncio
async def test_delete_chronicle_does_not_touch_directory_for_linked_chronicle(tmp_path):
    """A linked chronicle's project.db lives wherever the user pointed it - outside
    the workspace, on purpose. Deleting the archive record must never delete that."""
    from chronicler.core.models import Chronicle

    chronicle_id = uuid4()
    external_dir = tmp_path / "elsewhere"
    external_dir.mkdir()
    (external_dir / "project.db").write_text("data")

    repo = MagicMock(spec=ChronicleRepository)
    repo.get_by_id = AsyncMock(
        return_value=Chronicle(
            id=chronicle_id, title="Linked", project_path=str(external_dir / "project.db")
        )
    )
    repo.delete = AsyncMock()
    db_manager = MagicMock(workspace_path=tmp_path)

    service = ChronicleService(repo, db_manager)
    await service.delete_chronicle(chronicle_id)

    assert external_dir.exists()
    assert (external_dir / "project.db").exists()


@pytest.mark.asyncio
async def test_add_audio_source_moves_file_into_durable_sources_dir(tmp_path):
    chronicle_id = uuid4()
    staged_file = tmp_path / "imports" / "a1b2c3.mp3"
    staged_file.parent.mkdir(parents=True)
    staged_file.write_bytes(b"fake audio")

    db_manager = MagicMock(workspace_path=tmp_path)
    db_manager.get_chronicle_sources_path.return_value = (
        tmp_path / "chronicles" / str(chronicle_id) / "sources"
    )
    (tmp_path / "chronicles" / str(chronicle_id) / "sources").mkdir(parents=True)

    service = ChronicleService(MagicMock(), db_manager)
    result = await service.add_audio_source(chronicle_id, str(staged_file), "recording.mp3")

    assert not staged_file.exists()
    dest = tmp_path / "chronicles" / str(chronicle_id) / "sources" / "recording.mp3"
    assert dest.exists()
    assert result == str(dest)


@pytest.mark.asyncio
async def test_add_audio_source_avoids_overwriting_same_name(tmp_path):
    chronicle_id = uuid4()
    sources_dir = tmp_path / "chronicles" / str(chronicle_id) / "sources"
    sources_dir.mkdir(parents=True)
    (sources_dir / "recording.mp3").write_bytes(b"existing track")

    staged_file = tmp_path / "imports" / "a1b2c3.mp3"
    staged_file.parent.mkdir(parents=True)
    staged_file.write_bytes(b"new track")

    db_manager = MagicMock(workspace_path=tmp_path)
    db_manager.get_chronicle_sources_path.return_value = sources_dir

    service = ChronicleService(MagicMock(), db_manager)
    result = await service.add_audio_source(chronicle_id, str(staged_file), "recording.mp3")

    assert result == str(sources_dir / "recording (1).mp3")
    assert (sources_dir / "recording.mp3").read_bytes() == b"existing track"
    assert (sources_dir / "recording (1).mp3").read_bytes() == b"new track"


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
async def test_queue_transcribe_creates_transcribe_task():
    from chronicler.core.models import TaskType

    repo = MagicMock(spec=TaskRepository)
    repo.create = AsyncMock(side_effect=lambda x: x)

    service = TaskService(repo)
    task = await service.queue_transcribe(
        chronicle_id=uuid4(), file_path="/imports/audio.mp3", speaker_name="Alice"
    )

    assert task.type == TaskType.TRANSCRIBE
    assert json.loads(task.data)["file_path"] == "/imports/audio.mp3"
    assert json.loads(task.data)["speaker_name"] == "Alice"
