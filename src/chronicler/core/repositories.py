from abc import ABC, abstractmethod
from uuid import UUID

from chronicler.core.models import Chronicle, Tag, Task


class ChronicleRepository(ABC):
    @abstractmethod
    async def get_all(self) -> list[Chronicle]:
        pass

    @abstractmethod
    async def get_by_id(self, chronicle_id: UUID) -> Chronicle | None:
        pass

    @abstractmethod
    async def create(self, chronicle: Chronicle) -> Chronicle:
        pass

    @abstractmethod
    async def update(self, chronicle: Chronicle) -> Chronicle:
        pass

    @abstractmethod
    async def delete(self, chronicle_id: UUID) -> None:
        pass


class TagRepository(ABC):
    @abstractmethod
    async def get_all(self) -> list[Tag]:
        pass

    @abstractmethod
    async def create(self, tag: Tag) -> Tag:
        pass

    @abstractmethod
    async def delete(self, tag_id: UUID) -> None:
        pass


class TaskRepository(ABC):
    @abstractmethod
    async def get_all(self) -> list[Task]:
        pass

    @abstractmethod
    async def get_pending(self) -> list[Task]:
        pass

    @abstractmethod
    async def get_by_id(self, task_id: UUID) -> Task | None:
        pass

    @abstractmethod
    async def create(self, task: Task) -> Task:
        pass

    @abstractmethod
    async def update_status(self, task_id: UUID, status: str, error: str | None = None) -> None:
        pass

    @abstractmethod
    async def update_progress(self, task_id: UUID, progress: int) -> None:
        pass
