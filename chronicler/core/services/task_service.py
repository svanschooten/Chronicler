import json
from typing import Any
from uuid import UUID

from chronicler.core.models import Task, TaskStatus, TaskType
from chronicler.core.processing.regex_guard import assert_safe_pattern
from chronicler.core.repositories import TaskRepository
from chronicler.core.rpc import service


@service
class TaskService:
    def __init__(self, repository: TaskRepository):
        self.repository = repository

    async def list_tasks(self) -> list[Task]:
        return await self.repository.get_all()

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
            assert_safe_pattern(regex)
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
        return await self.repository.create(task)

    async def queue_clean(self, chronicle_id: UUID) -> Task:
        task = Task(
            type=TaskType.CLEAN,
            chronicle_id=chronicle_id,
        )
        return await self.repository.create(task)

    async def queue_transcribe(self, chronicle_id: UUID, file_path: str, speaker_name: str) -> Task:
        # One audio source = one speaker's track (no diarization yet - see
        # WorkerHandlers.handle_transcribe). Required, not optional: transcribing
        # without knowing whose track it is isn't a meaningful default, it's a
        # silent data-quality bug waiting to happen.
        task = Task(
            type=TaskType.TRANSCRIBE,
            chronicle_id=chronicle_id,
            data=json.dumps({"file_path": file_path, "speaker_name": speaker_name}),
        )
        return await self.repository.create(task)

    async def retry_task(self, task_id: UUID) -> None:
        """Puts a finished task back on the queue for one more attempt.

        Deliberately does *not* reset `attempts`, so one click buys exactly one attempt:
        the automatic retry budget is already spent by the time a task reaches FAILED, and
        refilling it would make a deterministically failing task (a bad regex, a missing
        file) fail three more times per click instead of once.
        """
        await self.repository.update_status(task_id, TaskStatus.PENDING)

    async def search_tasks(self, query: str) -> list[Task]:
        return await self.repository.search(query)
