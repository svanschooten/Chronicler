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

    @abstractmethod
    async def search(self, query: str) -> list[Chronicle]:
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

    @abstractmethod
    async def search(self, query: str) -> list[Tag]:
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
    async def claim_next(self, worker_id: str) -> Task | None:
        """Atomically claim one PENDING task (PENDING -> WORKING, stamped with
        worker_id/claimed_at) and return it, or None if there's nothing to claim.
        Safe under concurrent callers - at most one caller ever gets a given task.
        """
        pass

    @abstractmethod
    async def update_status(self, task_id: UUID, status: str, error: str | None = None) -> None:
        pass

    @abstractmethod
    async def mark_failed_or_retry(self, task_id: UUID, error: str) -> None:
        """Record a failed attempt. If the task still has attempts remaining, reset it
        to PENDING (clearing claimed_by/claimed_at) so it's eligible to be claimed
        again; otherwise mark it FAILED.
        """
        pass

    @abstractmethod
    async def update_progress(self, task_id: UUID, progress: int) -> None:
        pass

    @abstractmethod
    async def search(self, query: str) -> list[Task]:
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
    async def delete_all_lines(self) -> None:
        """Delete every transcript line. Deliberately does not touch speakers - see
        the SQLite implementation for why."""
        pass

    @abstractmethod
    async def search(self, query: str) -> list[TranscriptLine]:
        pass
