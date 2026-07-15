import json
from uuid import UUID

from chronicler.core.models import Task, TaskType
from chronicler.core.repositories import TaskRepository
from chronicler.core.rpc import service


@service
class TaskService:
    def __init__(self, repository: TaskRepository):
        self.repository = repository

    async def list_tasks(self) -> list[Task]:
        return await self.repository.get_all()

    async def queue_import(self, chronicle_id: UUID, file_path: str):
        task = Task(
            type=TaskType.IMPORT,
            chronicle_id=chronicle_id,
            data=json.dumps({"file_path": file_path}),
        )
        return await self.repository.create(task)

    async def queue_clean(self, chronicle_id: UUID):
        task = Task(
            type=TaskType.CLEAN,
            chronicle_id=chronicle_id,
        )
        return await self.repository.create(task)