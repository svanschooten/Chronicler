"""Shared plumbing for the task handlers."""

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

from chronicler.core.config import Settings, get_settings
from chronicler.core.database_manager import DatabaseManager
from chronicler.core.file_staging import confine_to_directory
from chronicler.core.models import Task, TranscriptLine
from chronicler.core.repositories import ChronicleRepository
from chronicler.core.sqlite import SQLiteTranscriptRepository

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int], Any]


class HandlerBase:
    def __init__(
        self,
        db_manager: DatabaseManager,
        chronicle_repo: ChronicleRepository | None = None,
        settings: Settings | None = None,
    ):
        self.db_manager = db_manager
        self.chronicle_repo = chronicle_repo
        self.settings = settings or get_settings()

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

    async def project_path_for(self, chronicle_id: UUID) -> Path | None:
        """
        A linked chronicle's project.db lives wherever the user put it, outside the
        workspace - None means the default in-workspace location.
        """
        if not self.chronicle_repo:
            return None
        chronicle = await self.chronicle_repo.get_by_id(chronicle_id)
        if chronicle and chronicle.project_path:
            return Path(chronicle.project_path)
        return None

    async def sources_root_for(self, chronicle_id: UUID) -> Path:
        """Where this chronicle's audio lives, linked or not - see docs/audio-sources.md."""
        return self.db_manager.sources_path_for(
            str(chronicle_id), await self.project_path_for(chronicle_id)
        )

    async def project_session(self, chronicle_id: UUID):
        return await self.db_manager.get_project_session(
            str(chronicle_id), custom_path=await self.project_path_for(chronicle_id)
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
        if self.chronicle_repo:
            await self.chronicle_repo.add_tag(chronicle_id, "Transcript")

    async def backfill_speakers_count(self, chronicle_id: UUID, count: int) -> None:
        if not self.chronicle_repo:
            return
        chronicle = await self.chronicle_repo.get_by_id(chronicle_id)
        if chronicle and chronicle.speakers_count != count:
            chronicle.speakers_count = count
            await self.chronicle_repo.update(chronicle)
