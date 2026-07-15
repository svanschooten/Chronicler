from abc import ABC, abstractmethod
from uuid import UUID

from chronicler.core.models import Chronicle, Speaker, Tag, Task, TranscriptLine


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


class TranscriptRepository(ABC):
    @abstractmethod
    async def get_speakers(self) -> list[Speaker]:
        pass

    @abstractmethod
    async def get_or_create_speaker(self, name: str) -> Speaker:
        pass

    @abstractmethod
    async def get_lines(self) -> list[TranscriptLine]:
        pass

    @abstractmethod
    async def add_line(self, line: TranscriptLine) -> TranscriptLine:
        pass

    @abstractmethod
    async def add_lines(self, lines: list[TranscriptLine]) -> None:
        pass

    @abstractmethod
    async def delete_all(self) -> None:
        pass
