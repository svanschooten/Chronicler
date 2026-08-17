"""The IMPORT task handler - parse a text transcript file into a chronicle's
project database."""

import logging

from chronicler.core.models import Task
from chronicler.core.processing.handlers.base import HandlerBase, ProgressCallback
from chronicler.core.processing.importers import DefaultImporter, RegexImporter
from chronicler.core.sqlite import SQLiteTranscriptRepository

logger = logging.getLogger(__name__)


class ImportHandler(HandlerBase):
    async def handle_import(self, task: Task, update_progress: ProgressCallback):
        chronicle_id = self.require_chronicle_id(task)
        data = self.task_data(task)
        file_path = self.require_field(data, "file_path", "import")
        resolved_path = self.confine_to(
            file_path, self.db_manager.get_imports_path(), "the imports directory"
        )

        logger.info(f"Importing transcript from {file_path} for chronicle {chronicle_id}")

        with open(resolved_path, encoding="utf-8") as f:
            content = f.read()

        lines = self._importer_for(data).parse(content)
        logger.info(f"Parsed {len(lines)} lines from {file_path}")

        await update_progress(50)

        # When appending, existing lines stay - only the new ones need to be ordered
        # after them. get_lines() orders by start_time, and RegexImporter emits
        # sequential 0-based start_time per file (see importers.py), so every append
        # needs its own lines shifted past whatever's already there.
        append = bool(data.get("append"))

        session = await self.project_session(chronicle_id)
        async with session:
            repo = SQLiteTranscriptRepository(session)
            try:
                if append:
                    existing_lines = await repo.get_lines()
                    offset = max((line.end_time for line in existing_lines), default=0.0)
                    for line in lines:
                        line.start_time += offset
                        line.end_time += offset
                else:
                    await repo.delete_all_lines()

                await self.attach_speakers(repo, lines)
                await repo.add_lines(lines)
                # One commit for the whole operation: a crash or exception at any point
                # before this leaves the previous transcript untouched, not
                # half-deleted (see the except block below).
                await session.commit()

                # Not len(speaker_map): in append mode that only counts speakers in the
                # *new* file, undercounting a chronicle that already had others.
                # Counting distinct names across every line now in the transcript is
                # correct in both modes.
                final_speaker_count = len({line.speaker_name for line in await repo.get_lines()})
            except Exception:
                await session.rollback()
                raise

        await self.tag_as_transcript(chronicle_id)
        await self.backfill_speakers_count(chronicle_id, final_speaker_count)

        await update_progress(100)
        logger.info(
            f"Transcript import finished for chronicle {chronicle_id}: "
            f"{len(lines)} lines, {final_speaker_count} speakers"
        )

    @staticmethod
    def _importer_for(data: dict) -> RegexImporter | DefaultImporter:
        regex = data.get("regex")
        if not regex:
            return DefaultImporter()
        return RegexImporter(
            regex,
            data.get("speaker_group", 1),
            data.get("text_group", 2),
            data.get("timestamp_group"),
        )
