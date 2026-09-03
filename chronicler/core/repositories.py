from abc import ABC, abstractmethod
from uuid import UUID

from chronicler.core.models import (
    AudioSource,
    Chronicle,
    KnownSpeaker,
    Speaker,
    Tag,
    Task,
    TranscriptLine,
)


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

    @abstractmethod
    async def add_tag(self, chronicle_id: UUID, tag_name: str) -> None:
        """
        Attach a tag to a chronicle, creating the tag if a tag with this name doesn't
        exist yet.
        """
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
        """
        Atomically claim one PENDING task (PENDING -> WORKING, stamped with
        worker_id/claimed_at) and return it, or None if there's nothing to claim.
        """
        pass

    @abstractmethod
    async def update_status(self, task_id: UUID, status: str, error: str | None = None) -> None:
        pass

    @abstractmethod
    async def mark_failed_or_retry(self, task_id: UUID, error: str) -> None:
        """Record a failed attempt."""
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
        """Delete every transcript line."""
        pass

    @abstractmethod
    async def delete_lines_by_speaker(self, speaker_id: UUID) -> None:
        """
        Delete only this speaker's lines, leaving every other speaker's lines untouched
        - used when re-transcribing a single audio source (one source = one speaker's
        track), not the whole chronicle's transcript.
        """
        pass

    @abstractmethod
    async def search(self, query: str) -> list[TranscriptLine]:
        pass


class AudioSourceRepository(ABC):
    @abstractmethod
    async def list_sources(self) -> list[AudioSource]:
        pass

    @abstractmethod
    async def get_by_filename(self, filename: str) -> AudioSource | None:
        pass

    @abstractmethod
    async def register(
        self,
        filename: str,
        content_hash: str | None = None,
        size_bytes: int | None = None,
        duration_seconds: float | None = None,
    ) -> AudioSource:
        """Creates the row for `filename`, or refreshes the content of an existing one."""

    @abstractmethod
    async def set_speaker(self, filename: str, speaker_id: UUID | None) -> None:
        pass

    @abstractmethod
    async def mark_transcribing(self, filename: str) -> None:
        pass

    @abstractmethod
    async def mark_transcribed(
        self, filename: str, content_hash: str | None, language: str | None, model: str | None
    ) -> None:
        pass

    @abstractmethod
    async def mark_transcription_failed(self, filename: str, error: str) -> None:
        pass

    @abstractmethod
    async def mark_normalizing(self, filename: str) -> None:
        pass

    @abstractmethod
    async def mark_normalized(
        self,
        filename: str,
        content_hash: str | None,
        normalized_filename: str,
        loudness_before: float | None = None,
        loudness_after: float | None = None,
    ) -> None:
        pass

    @abstractmethod
    async def mark_normalization_failed(self, filename: str, error: str) -> None:
        pass

    @abstractmethod
    async def delete(self, filename: str) -> None:
        pass


class KnownSpeakerRepository(ABC):
    """Speaker names seen anywhere in the workspace, so a picker can offer them all."""

    @abstractmethod
    async def register(self, name: str) -> KnownSpeaker | None:
        pass

    @abstractmethod
    async def list_speakers(self) -> list[KnownSpeaker]:
        pass

    @abstractmethod
    async def list_names(self) -> list[str]:
        pass

    @abstractmethod
    async def search(self, query: str) -> list[str]:
        pass
