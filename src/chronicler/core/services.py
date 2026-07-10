from chronicler.core.models import Chronicle, Task
from chronicler.core.repositories import ChronicleRepository, TaskRepository


class ChronicleService:
    def __init__(self, repository: ChronicleRepository):
        self.repository = repository

    async def list_chronicles(self) -> list[Chronicle]:
        return await self.repository.get_all()

    async def create_chronicle(self, title: str) -> Chronicle:
        chronicle = Chronicle(title=title)
        return await self.repository.create(chronicle)


class TaskService:
    def __init__(self, repository: TaskRepository):
        self.repository = repository

    async def list_tasks(self) -> list[Task]:
        return await self.repository.get_all()
