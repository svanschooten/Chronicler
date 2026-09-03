import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from chronicler.core.models import TaskStatus, TaskType
from chronicler.core.processing.regex_guard import UnsafePatternError
from chronicler.core.repositories import TaskRepository
from chronicler.core.services.task_service import TaskService


def _repository():
    """A task repository that hands back whatever it was asked to create."""
    repo = MagicMock(spec=TaskRepository)
    repo.create = AsyncMock(side_effect=lambda task: task)
    return repo


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
    task = await service.queue_import(chronicle_id=uuid4(), file_path="/imports/x.txt", append=True)

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


class TestTranscribeParameters:
    @pytest.mark.asyncio
    async def test_language_and_threshold_are_carried_on_the_task(self):
        repo = MagicMock(spec=TaskRepository)
        repo.create = AsyncMock(side_effect=lambda task: task)
        service = TaskService(repo)

        task = await service.queue_transcribe(
            uuid4(), "/s/a.wav", "GM", language="nl", no_speech_threshold=0.4, model_size="small"
        )

        data = json.loads(task.data)
        assert data["language"] == "nl"
        assert data["no_speech_threshold"] == 0.4
        assert data["model_size"] == "small"

    @pytest.mark.asyncio
    async def test_omitted_parameters_are_absent_so_settings_apply(self):
        repo = MagicMock(spec=TaskRepository)
        repo.create = AsyncMock(side_effect=lambda task: task)
        service = TaskService(repo)

        task = await service.queue_transcribe(uuid4(), "/s/a.wav", "GM")

        data = json.loads(task.data)
        assert "language" not in data
        assert "no_speech_threshold" not in data
        assert data == {"file_path": "/s/a.wav", "speaker_name": "GM"}

    @pytest.mark.asyncio
    async def test_auto_language_is_recorded_so_it_beats_a_configured_default(self):
        repo = MagicMock(spec=TaskRepository)
        repo.create = AsyncMock(side_effect=lambda task: task)
        service = TaskService(repo)

        task = await service.queue_transcribe(uuid4(), "/s/a.wav", "GM", language="auto")

        assert json.loads(task.data)["language"] == "auto"

    @pytest.mark.asyncio
    async def test_normalize_first_is_carried(self):
        repo = MagicMock(spec=TaskRepository)
        repo.create = AsyncMock(side_effect=lambda task: task)
        service = TaskService(repo)

        task = await service.queue_transcribe(uuid4(), "/s/a.wav", "GM", normalize_first=True)

        assert json.loads(task.data)["normalize_first"] is True


class TestQueueNormalize:
    @pytest.mark.asyncio
    async def test_it_carries_the_file_path(self):
        repo = _repository()
        service = TaskService(repo)

        task = await service.queue_normalize(uuid4(), "/sources/gm.wav")

        assert task.type == TaskType.NORMALIZE
        assert json.loads(task.data)["file_path"] == "/sources/gm.wav"

    @pytest.mark.asyncio
    async def test_force_is_absent_unless_asked_for(self):
        """An absent key lets the handler skip work that is already done."""
        task = await TaskService(_repository()).queue_normalize(uuid4(), "/sources/gm.wav")

        assert "force" not in json.loads(task.data)

    @pytest.mark.asyncio
    async def test_force_is_recorded_when_asked_for(self):
        task = await TaskService(_repository()).queue_normalize(
            uuid4(), "/sources/gm.wav", force=True
        )

        assert json.loads(task.data)["force"] is True


class TestQueueSummarize:
    @pytest.mark.asyncio
    async def test_an_unconfigured_run_carries_no_overrides(self):
        """No keys at all, so every value falls back to the configured defaults."""
        task = await TaskService(_repository()).queue_summarize(uuid4())

        assert task.type == TaskType.SUMMARIZE
        assert json.loads(task.data) == {}

    @pytest.mark.asyncio
    async def test_model_and_title_sit_at_the_top_level(self):
        task = await TaskService(_repository()).queue_summarize(
            uuid4(), model="qwen3", title="First pass"
        )

        data = json.loads(task.data)
        assert data["model"] == "qwen3"
        assert data["title"] == "First pass"

    @pytest.mark.asyncio
    async def test_prompt_overrides_are_nested_under_summary(self):
        """The handler merges data["summary"] over SummarySettings, so shape matters."""
        task = await TaskService(_repository()).queue_summarize(
            uuid4(), recap_prompt="Be brief.", language="nl"
        )

        assert json.loads(task.data)["summary"] == {
            "recap_prompt": "Be brief.",
            "language": "nl",
        }

    @pytest.mark.asyncio
    async def test_only_the_overrides_given_are_recorded(self):
        task = await TaskService(_repository()).queue_summarize(
            uuid4(), system_prompt="You are terse."
        )

        assert json.loads(task.data)["summary"] == {"system_prompt": "You are terse."}

    @pytest.mark.asyncio
    async def test_no_summary_key_when_no_prompt_was_overridden(self):
        task = await TaskService(_repository()).queue_summarize(uuid4(), model="qwen3")

        assert "summary" not in json.loads(task.data)

    @pytest.mark.asyncio
    async def test_an_empty_title_is_not_recorded_as_a_title(self):
        task = await TaskService(_repository()).queue_summarize(uuid4(), title="")

        assert "title" not in json.loads(task.data)
