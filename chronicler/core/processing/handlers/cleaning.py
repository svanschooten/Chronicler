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

                await repo.delete_all_lines()
                speaker_map = await self.attach_speakers(repo, cleaned_lines)
                await repo.add_lines(cleaned_lines)
                await session.commit()
            except Exception:
                await session.rollback()
                raise

        # Cleaning only ever merges or drops lines from one existing transcript, so
        # the speaker map it just built covers the whole thing - no need to re-read
        # every line back the way an append-capable import does.
        await self.backfill_speakers_count(chronicle_id, len(speaker_map))

        await update_progress(100)
        logger.info(
            f"Transcript clean finished for chronicle {chronicle_id}: "
            f"{len(cleaned_lines)} lines, {len(speaker_map)} speakers"
        )
