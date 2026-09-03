"""
The CLEAN task handler - re-run the transcript cleaner over lines already in a chronicle's
project database.
"""

import logging

from pydantic import ValidationError

from chronicler.core.config_sections import CleaningSettings
from chronicler.core.models import Task
from chronicler.core.processing.cleaners import TranscriptCleaner
from chronicler.core.processing.handlers.base import HandlerBase, ProgressCallback
from chronicler.core.sqlite import SQLiteTranscriptRepository

logger = logging.getLogger(__name__)


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

        session = await self.project_session(chronicle_id)
        async with session:
            repo = SQLiteTranscriptRepository(session)
            try:
                lines = await repo.get_lines()
                logger.info(f"Cleaning {len(lines)} lines for chronicle {chronicle_id}")

                await update_progress(30)

                cleaned_lines = TranscriptCleaner(cleaning).clean(lines)
                logger.info(f"Cleaned down to {len(cleaned_lines)} lines")

                await update_progress(70)

                await repo.delete_all_lines()
                await repo.add_lines(cleaned_lines)
                await session.commit()
            except Exception:
                await session.rollback()
                raise

        speakers_count = len({line.speaker_name for line in cleaned_lines})
        await self.backfill_speakers_count(chronicle_id, speakers_count)

        await update_progress(100)
        logger.info(
            f"Transcript clean finished for chronicle {chronicle_id}: "
            f"{len(cleaned_lines)} lines, {speakers_count} speakers"
        )
