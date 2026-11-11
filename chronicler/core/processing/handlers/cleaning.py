"""
The CLEAN task handler - re-run the transcript cleaner over lines already in a chronicle's
project database.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from chronicler.core.config_sections import CleaningSettings
from chronicler.core.models import Task, TranscriptLine
from chronicler.core.processing.cleaners import TranscriptCleaner
from chronicler.core.processing.handlers.base import HandlerBase, ProgressCallback
from chronicler.core.sqlite import SQLiteTranscriptRepository

logger = logging.getLogger(__name__)

SNAPSHOTS_KEPT = 3
"""
How many before-clean snapshots a chronicle keeps: the oldest, which holds the
transcript as it was before any clean, and the newest of the rest.
"""

CLEAN_ATTEMPTS = 3
"""How many times a clean starts again when the transcript changed while it ran."""


class CleanHandler(HandlerBase):
    def cleaning_settings(self, task: Task) -> CleaningSettings:
        """The task's own cleaning override if it carries one, otherwise the configured default."""
        override = self.task_data(task).get("cleaning")
        if not override:
            return self.settings.cleaning
        try:
            return CleaningSettings(**override)
        except ValidationError as error:
            raise ValueError(
                f"Invalid cleaning configuration on task {task.id}: {error}"
            ) from error

    async def handle_clean(self, task: Task, update_progress: ProgressCallback):
        chronicle_id = self.require_chronicle_id(task)
        cleaning = self.cleaning_settings(task)
        logger.info(f"Cleaning transcript for chronicle {chronicle_id}")

        # Before the transaction: VACUUM INTO cannot run inside one. A failed snapshot
        # fails the task, so nothing is rewritten without a copy to go back to.
        snapshot = await self.snapshot_before_clean(chronicle_id)
        logger.info(f"Saved the transcript before cleaning to {snapshot}")

        cleaned_lines = await self._clean_lines(chronicle_id, cleaning, update_progress)

        speakers_count = len({line.speaker_name for line in cleaned_lines})
        await self.backfill_speakers_count(chronicle_id, speakers_count)

        await update_progress(100)
        logger.info(
            f"Transcript clean finished for chronicle {chronicle_id}: "
            f"{len(cleaned_lines)} lines, {speakers_count} speakers"
        )

    async def _clean_lines(
        self, chronicle_id: UUID, cleaning: CleaningSettings, update_progress: ProgressCallback
    ) -> list[TranscriptLine]:
        """
        Cleans outside any transaction, then writes the result only if the lines it read
        are still the lines there.

        Cleaning can take up to the regex time limit. Holding the transaction across it
        made every edit to this chronicle fail with "database is locked" meanwhile. An
        edit that lands while cleaning runs is not overwritten: the clean starts again from
        the new lines, and gives up after `CLEAN_ATTEMPTS`. See docs/storage.md.
        """
        for _ in range(CLEAN_ATTEMPTS):
            async with await self.project_session(chronicle_id) as session:
                lines = await SQLiteTranscriptRepository(session).get_lines()
            logger.info(f"Cleaning {len(lines)} lines for chronicle {chronicle_id}")
            await update_progress(30)

            cleaned_lines = await asyncio.to_thread(TranscriptCleaner(cleaning).clean, lines)
            logger.info(f"Cleaned down to {len(cleaned_lines)} lines")
            await update_progress(70)

            async with self.transaction(chronicle_id) as session:
                repo = SQLiteTranscriptRepository(session)
                if await repo.get_lines() == lines:
                    await repo.delete_all_lines()
                    await repo.add_lines(cleaned_lines)
                    return cleaned_lines
            logger.info(f"Chronicle {chronicle_id} changed while it was cleaned; starting again")
        raise RuntimeError(
            "The transcript kept changing while it was being cleaned. Run Clean again once "
            "nothing else is editing it."
        )

    async def snapshot_before_clean(self, chronicle_id: UUID) -> Path:
        """
        Copies the chronicle's database to `snapshots/before-clean-<id>-<time>.db` beside
        its project.db. Cleaning drops and merges lines, and the text it removes cannot
        be regenerated. See docs/cleaning.md.

        The name carries the chronicle id because linked chronicles whose databases share
        a folder share its `snapshots/`, and pruning one must not touch another's copies.
        """
        must_exist = self.archive_sessions is not None
        # Checked before the snapshots folder is made beside a linked file that has moved.
        project_path = await self.db_manager.project_path_for(chronicle_id, must_exist=must_exist)
        directory = self.db_manager.snapshots_path_for(str(chronicle_id), project_path)
        prefix = f"before-clean-{chronicle_id}-"
        destination = directory / f"{prefix}{datetime.now():%Y%m%d-%H%M%S-%f}.db"
        await self.db_manager.snapshot_project(chronicle_id, destination, must_exist=must_exist)

        snapshots = sorted(directory.glob(f"{prefix}*.db"))
        oldest, rest = snapshots[:1], snapshots[1:]
        for old in rest[: max(len(rest) - (SNAPSHOTS_KEPT - len(oldest)), 0)]:
            old.unlink()
        return destination
