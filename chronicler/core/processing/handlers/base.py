"""Shared plumbing for the task handlers.

Every handler follows the same shape: look up the chronicle, open a session against
its project database, rewrite transcript lines inside one transaction, then backfill
whatever chronicle metadata the operation just made stale. That shape lives here so
each handler module only contains what makes it different.
"""

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.file_staging import confine_to_directory
from chronicler.core.models import Task, TranscriptLine
from chronicler.core.repositories import ChronicleRepository
from chronicler.core.sqlite import SQLiteTranscriptRepository

logger = logging.getLogger(__name__)

#: A handler's progress reporter, supplied by WorkerManager.
ProgressCallback = Callable[[int], Any]


class HandlerBase:
    def __init__(
        self, db_manager: DatabaseManager, chronicle_repo: ChronicleRepository | None = None
    ):
        self.db_manager = db_manager
        # Optional: without it a handler still rewrites the transcript correctly, it
        # just can't tag the chronicle or backfill its derived metadata. Tests that
        # only care about transcript contents leave it out.
        self.chronicle_repo = chronicle_repo

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
        """Rejects a `file_path` that resolves outside `root`.

        The path arrives from the RPC caller and is not trustworthy on its own, so
        it's checked right at the point of access - which covers every caller
        regardless of how they obtained the string, not just ones that went through
        the /upload endpoint. One implementation, in file_staging.py, shared with the
        services that take a path over RPC too.
        """
        return confine_to_directory(file_path, root, description)

    async def project_path_for(self, chronicle_id: UUID) -> Path | None:
        """A linked chronicle's project.db lives wherever the user put it, outside the
        workspace - None means the default in-workspace location."""
        if not self.chronicle_repo:
            return None
        chronicle = await self.chronicle_repo.get_by_id(chronicle_id)
        if chronicle and chronicle.project_path:
            return Path(chronicle.project_path)
        return None

    async def project_session(self, chronicle_id: UUID):
        return await self.db_manager.get_project_session(
            str(chronicle_id), custom_path=await self.project_path_for(chronicle_id)
        )

    @staticmethod
    async def attach_speakers(
        repo: SQLiteTranscriptRepository, lines: list[TranscriptLine]
    ) -> dict[str | None, UUID]:
        """Resolves each line's speaker name to a speaker row, creating rows as
        needed, and stamps `speaker_id` onto the lines in place. Returns the
        name -> id map so a caller can tell how many distinct speakers it just saw.
        """
        speaker_map: dict[str | None, UUID] = {}
        for line in lines:
            if line.speaker_name not in speaker_map:
                # TranscriptLine.speaker_name is typed str | None for the general
                # case, but every current producer (RegexImporter, TranscriptCleaner,
                # transcribe_audio) always sets a real string. Pre-existing gap.
                speaker = await repo.get_or_create_speaker(line.speaker_name)  # type: ignore[arg-type]
                speaker_map[line.speaker_name] = speaker.id
            line.speaker_id = speaker_map[line.speaker_name]
        return speaker_map

    async def tag_as_transcript(self, chronicle_id: UUID) -> None:
        if self.chronicle_repo:
            await self.chronicle_repo.add_tag(chronicle_id, "Transcript")

    async def backfill_speakers_count(self, chronicle_id: UUID, count: int) -> None:
        # RegexImporter/TranscriptCleaner already produce a full speaker map as a side
        # effect of parsing - this is free, not a separate "identify speakers" pass, so
        # it always runs rather than needing an opt-in. See also
        # TranscriptService.refresh_speaker_count for the manual reconciliation path
        # (edited transcripts, or chronicles imported before this existed).
        if not self.chronicle_repo:
            return
        chronicle = await self.chronicle_repo.get_by_id(chronicle_id)
        if chronicle and chronicle.speakers_count != count:
            chronicle.speakers_count = count
            await self.chronicle_repo.update(chronicle)
