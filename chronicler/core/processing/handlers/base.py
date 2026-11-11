"""Shared plumbing for the task handlers."""

import json
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.config import Settings, get_settings
from chronicler.core.database_manager import DatabaseManager
from chronicler.core.file_staging import confine_to_directory
from chronicler.core.models import Task, TranscriptLine
from chronicler.core.sqlite import SQLiteChronicleRepository, SQLiteTranscriptRepository

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int], Any]


class HandlerBase:
    def __init__(
        self,
        db_manager: DatabaseManager,
        archive_sessions: Callable[[], AsyncSession] | None = None,
        settings: Settings | None = None,
    ):
        self.db_manager = db_manager
        self.archive_sessions = archive_sessions
        self.settings = settings or get_settings()

    @asynccontextmanager
    async def chronicles(self) -> AsyncIterator[SQLiteChronicleRepository]:
        """
        A chronicle repository on a short archive session of its own. Without
        `archive_sessions` a handler skips its chronicle bookkeeping, so check that first.
        """
        assert self.archive_sessions is not None
        async with self.archive_sessions() as session:
            yield SQLiteChronicleRepository(session)

    @staticmethod
    def require_chronicle_id(task: Task) -> UUID:
        if not task.chronicle_id:
            raise ValueError("Task has no chronicle_id")
        return task.chronicle_id

    @staticmethod
    def task_data(task: Task) -> dict[str, Any]:
        return json.loads(task.data) if task.data else {}

    @staticmethod
    def require_field(data: dict[str, Any], field: str, task_kind: str) -> Any:
        value = data.get(field)
        if not value:
            raise ValueError(f"No {field} provided for {task_kind} task")
        return value

    @staticmethod
    def confine_to(file_path: str, root: Path, description: str) -> Path:
        """Rejects a `file_path` that resolves outside `root`."""
        return confine_to_directory(file_path, root, description)

    async def sources_root_for(self, chronicle_id: UUID) -> Path:
        """Where this chronicle's audio lives, linked or not - see docs/audio-sources.md."""
        return self.db_manager.sources_path_for(
            str(chronicle_id), await self.db_manager.project_path_for(chronicle_id)
        )

    def transaction(self, chronicle_id: UUID):
        """
        A project database transaction - see `DatabaseManager.transaction`. Raises
        LookupError for a chronicle with no row (deleted while the task waited) and
        FileNotFoundError for a linked one whose file has moved, instead of creating a
        new empty database. Without `archive_sessions` (tests only) that check is skipped,
        but the location is still read from the archive, so the chronicle needs a row.
        """
        return self.db_manager.transaction(
            chronicle_id, must_exist=self.archive_sessions is not None
        )

    async def project_session(self, chronicle_id: UUID):
        """A read-only project session, checked like `transaction`. The caller closes it."""
        return await self.db_manager.get_project_session(
            chronicle_id, must_exist=self.archive_sessions is not None
        )

    async def snapshot_before(self, chronicle_id: UUID, kind: str) -> Path:
        """
        A copy of the chronicle's database to restore from, made before `kind` (clean,
        import, transcribe) replaces its text. A failed snapshot fails the task, so nothing
        is rewritten without a copy to go back to. See docs/storage.md.
        """
        return await self.db_manager.snapshot_before(
            chronicle_id, kind, must_exist=self.archive_sessions is not None
        )

    @staticmethod
    async def attach_speakers(
        repo: SQLiteTranscriptRepository, lines: list[TranscriptLine]
    ) -> dict[str | None, UUID]:
        """
        Resolves each line's speaker name to a speaker row, creating rows as needed, and
        stamps `speaker_id` onto the lines in place.
        """
        speaker_map: dict[str | None, UUID] = {}
        for line in lines:
            if line.speaker_name not in speaker_map:
                speaker = await repo.get_or_create_speaker(line.speaker_name)  # type: ignore[arg-type]
                speaker_map[line.speaker_name] = speaker.id
            line.speaker_id = speaker_map[line.speaker_name]
        return speaker_map

    async def tag_as_transcript(self, chronicle_id: UUID) -> None:
        if self.archive_sessions:
            async with self.chronicles() as chronicles:
                await chronicles.add_tag(chronicle_id, "Transcript")

    async def backfill_speakers_count(self, chronicle_id: UUID, count: int) -> None:
        if not self.archive_sessions:
            return
        async with self.chronicles() as chronicles:
            chronicle = await chronicles.get_by_id(chronicle_id)
            if chronicle and chronicle.speakers_count != count:
                chronicle.speakers_count = count
                await chronicles.update(chronicle)
