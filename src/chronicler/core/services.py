import json
from uuid import UUID

from chronicler.core.models import Chronicle, Task, TaskType
from chronicler.core.repositories import ChronicleRepository, TaskRepository


class ChronicleService:
    def __init__(self, repository: ChronicleRepository):
        self.repository = repository

    async def list_chronicles(self) -> list[Chronicle]:
        return await self.repository.get_all()

    async def get_chronicle(self, chronicle_id: UUID) -> Chronicle | None:
        return await self.repository.get_by_id(chronicle_id)

    async def create_chronicle(self, title: str) -> Chronicle:
        chronicle = Chronicle(title=title)
        return await self.repository.create(chronicle)


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
