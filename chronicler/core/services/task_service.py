import json
from typing import Any
from uuid import UUID

from chronicler.core.models import Task, TaskType
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
    ):
        data: dict[str, Any] = {"file_path": file_path}
        if regex:
            assert_safe_pattern(regex)
            data["regex"] = regex
            data["speaker_group"] = speaker_group
            data["text_group"] = text_group

        task = Task(
            type=TaskType.IMPORT,
            chronicle_id=chronicle_id,
            data=json.dumps(data),
        )
        return await self.repository.create(task)

    async def queue_clean(self, chronicle_id: UUID):
        task = Task(
            type=TaskType.CLEAN,
            chronicle_id=chronicle_id,
        )
        return await self.repository.create(task)

    async def search_tasks(self, query: str) -> list[Task]:
        return await self.repository.search(query)
