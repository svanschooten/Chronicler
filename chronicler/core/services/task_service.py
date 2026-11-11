import json
from typing import Any
from uuid import UUID

from chronicler.core.models import Task, TaskStatus, TaskType
from chronicler.core.processing.regex_guard import compile_pattern
from chronicler.core.repositories import TaskRepository
from chronicler.core.rpc import service

# A rerun of a transcription is expensive and a manual retry exists, so it is not repeated
# automatically. Every other type keeps the model's default.
CANCELLABLE_WHILE_WORKING = {TaskType.TRANSCRIBE}
"""Task types whose handler checks for cancellation as it runs."""
FINISHED_LIST_LIMIT = 200

MAX_ATTEMPTS: dict[TaskType, int] = {TaskType.TRANSCRIBE: 1}


@service(
    expose=[
        "cancel_task",
        "clear_finished_tasks",
        "list_tasks",
        "queue_clean",
        "queue_import",
        "queue_normalize",
        "queue_summarize",
        "queue_transcribe",
        "retry_task",
        "search_tasks",
    ]
)
class TaskService:
    def __init__(self, repository: TaskRepository):
        self.repository = repository

    async def _create(self, task: Task) -> Task:
        """Every queued task goes through here, so its type's attempt budget applies."""
        task.max_attempts = MAX_ATTEMPTS.get(task.type, task.max_attempts)
        return await self.repository.create(task)

    async def list_tasks(
        self, include_finished: bool = False, limit: int = FINISHED_LIST_LIMIT
    ) -> list[Task]:
        """
        Newest first. Unfinished tasks are always all there; with `include_finished` the
        list is capped at `limit`, so its size does not grow with the task history.
        """
        if include_finished:
            return await self.repository.get_all(limit=limit)
        return await self.repository.get_all(include_finished=False)

    async def clear_finished_tasks(self, include_failed: bool = False) -> int:
        """Deletes DONE tasks, and FAILED ones too when asked. Returns how many went."""
        return await self.repository.delete_finished(include_failed=include_failed)

    async def queue_import(
        self,
        chronicle_id: UUID,
        file_path: str,
        regex: str | None = None,
        speaker_group: int = 1,
        text_group: int = 2,
        timestamp_group: int | None = None,
        append: bool = False,
    ) -> Task:
        data: dict[str, Any] = {"file_path": file_path}
        if regex:
            compile_pattern(regex)
            data["regex"] = regex
            data["speaker_group"] = speaker_group
            data["text_group"] = text_group
            if timestamp_group is not None:
                data["timestamp_group"] = timestamp_group
        if append:
            data["append"] = True

        task = Task(
            type=TaskType.IMPORT,
            chronicle_id=chronicle_id,
            data=json.dumps(data),
        )
        return await self._create(task)

    async def queue_clean(self, chronicle_id: UUID) -> Task:
        task = Task(
            type=TaskType.CLEAN,
            chronicle_id=chronicle_id,
        )
        return await self._create(task)

    async def queue_transcribe(
        self,
        chronicle_id: UUID,
        file_path: str,
        speaker_name: str,
        language: str | None = None,
        no_speech_threshold: float | None = None,
        model_size: str | None = None,
        normalize_first: bool | None = None,
        start_offset: float | None = None,
    ) -> Task:
        """
        Queues one track. Omitted parameters fall back to the configured defaults, and an
        omitted `start_offset` keeps the one stored on the track.
        """
        data: dict[str, Any] = {"file_path": file_path, "speaker_name": speaker_name}
        if language is not None:
            data["language"] = language
        if no_speech_threshold is not None:
            data["no_speech_threshold"] = no_speech_threshold
        if model_size is not None:
            data["model_size"] = model_size
        if normalize_first is not None:
            data["normalize_first"] = normalize_first
        if start_offset is not None:
            data["start_offset"] = start_offset

        task = Task(
            type=TaskType.TRANSCRIBE,
            chronicle_id=chronicle_id,
            data=json.dumps(data),
        )
        return await self._create(task)

    async def queue_normalize(
        self, chronicle_id: UUID, file_path: str, force: bool = False
    ) -> Task:
        """Queues loudness normalization of one audio source."""
        data: dict[str, Any] = {"file_path": file_path}
        if force:
            data["force"] = True
        return await self._create(
            Task(type=TaskType.NORMALIZE, chronicle_id=chronicle_id, data=json.dumps(data))
        )

    async def queue_summarize(
        self,
        chronicle_id: UUID,
        model: str | None = None,
        title: str | None = None,
        recap_prompt: str | None = None,
        chunk_prompt: str | None = None,
        system_prompt: str | None = None,
        language: str | None = None,
    ) -> Task:
        """Queues one summary run. Prompt overrides apply to this run only."""
        data: dict[str, Any] = {}
        if model:
            data["model"] = model
        if title:
            data["title"] = title

        overrides = {
            "recap_prompt": recap_prompt,
            "chunk_prompt": chunk_prompt,
            "system_prompt": system_prompt,
            "language": language,
        }
        summary = {key: value for key, value in overrides.items() if value is not None}
        if summary:
            data["summary"] = summary

        return await self._create(
            Task(type=TaskType.SUMMARIZE, chronicle_id=chronicle_id, data=json.dumps(data))
        )

    async def cancel_task(self, task_id: UUID) -> bool:
        """
        Cancels a task that has not finished. A queued one never runs. A running one is
        stopped only if its type can notice (`CANCELLABLE_WHILE_WORKING`): the rest are
        short, and cancelling one would only relabel work that carries on. Returns whether
        the task was cancelled.
        """
        task = await self.repository.get_by_id(task_id)
        if task is None:
            return False
        return await self.repository.cancel(
            task_id, while_working=task.type in CANCELLABLE_WHILE_WORKING
        )

    async def retry_task(self, task_id: UUID) -> None:
        """Puts a finished task back on the queue for one more attempt."""
        await self.repository.update_status(task_id, TaskStatus.PENDING)

    async def search_tasks(self, query: str) -> list[Task]:
        return await self.repository.search(query)
