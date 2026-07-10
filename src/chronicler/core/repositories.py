from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID
from chronicler.core.models import Chronicle, Tag

class ChronicleRepository(ABC):
    @abstractmethod
    async def get_all(self) -> List[Chronicle]:
        pass

    @abstractmethod
    async def get_by_id(self, chronicle_id: UUID) -> Optional[Chronicle]:
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
    async def get_all(self) -> List[Tag]:
        pass

    @abstractmethod
    async def create(self, tag: Tag) -> Tag:
        pass

    @abstractmethod
    async def delete(self, tag_id: UUID) -> None:
        pass

class TaskRepository(ABC):
    @abstractmethod
    async def get_all(self) -> List[dict]: # Using dict for now as Task model is simple
        pass

    @abstractmethod
    async def create(self, task_data: dict) -> dict:
        pass

    @abstractmethod
    async def update_status(self, task_id: UUID, status: str, error: Optional[str] = None) -> None:
        pass
