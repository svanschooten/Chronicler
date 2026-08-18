"""The CLEAN task handler - re-run the transcript cleaner over lines already in a
chronicle's project database."""

import logging

from chronicler.core.models import Task
from chronicler.core.processing.cleaners import TranscriptCleaner
from chronicler.core.processing.handlers.base import HandlerBase, ProgressCallback
from chronicler.core.sqlite import SQLiteTranscriptRepository

logger = logging.getLogger(__name__)


class CleanHandler(HandlerBase):
    async def handle_clean(self, task: Task, update_progress: ProgressCallback):
        chronicle_id = self.require_chronicle_id(task)
        logger.info(f"Cleaning transcript for chronicle {chronicle_id}")

        session = await self.project_session(chronicle_id)
        async with session:
            repo = SQLiteTranscriptRepository(session)
            try:
                lines = await repo.get_lines()
                logger.info(f"Cleaning {len(lines)} lines for chronicle {chronicle_id}")

                await update_progress(30)

                cleaned_lines = TranscriptCleaner().clean(lines)
                logger.info(f"Cleaned down to {len(cleaned_lines)} lines")

                await update_progress(70)

                # No attach_speakers here (contrast with the import handler): these
                # lines came out of this same database, so they already carry the
                # speaker_id of a row that delete_all_lines() leaves in place.
                # Resolving each name back to that same id would be a query per
                # speaker to learn what the lines already say.
                await repo.delete_all_lines()
                await repo.add_lines(cleaned_lines)
                await session.commit()
            except Exception:
                await session.rollback()
                raise

        # Cleaning only ever merges or drops lines from one existing transcript, so
        # the names on the cleaned lines cover the whole thing - no need to re-read
        # every line back the way an append-capable import does.
        speakers_count = len({line.speaker_name for line in cleaned_lines})
        await self.backfill_speakers_count(chronicle_id, speakers_count)

        await update_progress(100)
        logger.info(
            f"Transcript clean finished for chronicle {chronicle_id}: "
            f"{len(cleaned_lines)} lines, {speakers_count} speakers"
        )
