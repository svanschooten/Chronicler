import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import Task
from chronicler.core.processing.cleaners import TranscriptCleaner
from chronicler.core.processing.importers import DefaultImporter, RegexImporter
from chronicler.core.sqlite import SQLiteTranscriptRepository

logger = logging.getLogger(__name__)


class WorkerHandlers:
    def __init__(self, db_manager: DatabaseManager, chronicle_repo=None):
        self.db_manager = db_manager
        self.chronicle_repo = chronicle_repo

    async def handle_import(self, task: Task, update_progress: Callable[[int], Any]):
        if not task.chronicle_id:
            raise ValueError("Task has no chronicle_id")

        custom_path = None
        if self.chronicle_repo:
            chronicle = await self.chronicle_repo.get_by_id(task.chronicle_id)
            if chronicle and chronicle.project_path:
                custom_path = Path(chronicle.project_path)

        data = json.loads(task.data) if task.data else {}
        file_path = data.get("file_path")
        if not file_path:
            raise ValueError("No file_path provided for import task")

        # file_path arrives from the RPC caller (TaskService.queue_import) and is not
        # trustworthy on its own - confine it to the imports directory right at the
        # point of access, which covers every caller regardless of how they obtained a
        # file_path string, not just ones that went through the /upload endpoint.
        resolved_path = Path(file_path).resolve()
        imports_root = self.db_manager.get_imports_path().resolve()
        if not resolved_path.is_relative_to(imports_root):
            raise ValueError(f"file_path must be inside the imports directory: {file_path}")

        logger.info(f"Importing transcript from {file_path} for chronicle {task.chronicle_id}")

        with open(resolved_path, encoding="utf-8") as f:
            content = f.read()

        regex = data.get("regex")
        if regex:
            speaker_group = data.get("speaker_group", 1)
            text_group = data.get("text_group", 2)
            importer = RegexImporter(regex, speaker_group, text_group)
        else:
            importer = DefaultImporter()

        lines = importer.parse(content)

        await update_progress(50)

        session = await self.db_manager.get_project_session(
            str(task.chronicle_id), custom_path=custom_path
        )
        async with session:
            repo = SQLiteTranscriptRepository(session)
            try:
                await repo.delete_all_lines()

                final_lines = []
                speaker_map = {}
                for line in lines:
                    if line.speaker_name not in speaker_map:
                        # TranscriptLine.speaker_name is typed str | None for the
                        # general case, but every current producer (RegexImporter,
                        # TranscriptCleaner) always sets a real string. Pre-existing
                        # gap, not addressed here.
                        speaker = await repo.get_or_create_speaker(line.speaker_name)  # type: ignore[arg-type]
                        speaker_map[line.speaker_name] = speaker.id

                    line.speaker_id = speaker_map[line.speaker_name]
                    final_lines.append(line)

                await repo.add_lines(final_lines)
                # One commit for the whole operation: a crash or exception at any
                # point before this leaves the previous transcript untouched, not
                # half-deleted (see the except block below).
                await session.commit()
            except Exception:
                await session.rollback()
                raise

        await update_progress(100)

    async def handle_clean(self, task: Task, update_progress: Callable[[int], Any]):
        if not task.chronicle_id:
            raise ValueError("Task has no chronicle_id")

        logger.info(f"Cleaning transcript for chronicle {task.chronicle_id}")

        custom_path = None
        if self.chronicle_repo:
            chronicle = await self.chronicle_repo.get_by_id(task.chronicle_id)
            if chronicle and chronicle.project_path:
                custom_path = Path(chronicle.project_path)

        session = await self.db_manager.get_project_session(
            str(task.chronicle_id), custom_path=custom_path
        )
        async with session:
            repo = SQLiteTranscriptRepository(session)
            try:
                lines = await repo.get_lines()

                await update_progress(30)

                cleaner = TranscriptCleaner()
                cleaned_lines = cleaner.clean(lines)

                await update_progress(70)

                await repo.delete_all_lines()

                final_lines = []
                speaker_map = {}
                for line in cleaned_lines:
                    if line.speaker_name not in speaker_map:
                        # TranscriptLine.speaker_name is typed str | None for the
                        # general case, but every current producer (RegexImporter,
                        # TranscriptCleaner) always sets a real string. Pre-existing
                        # gap, not addressed here.
                        speaker = await repo.get_or_create_speaker(line.speaker_name)  # type: ignore[arg-type]
                        speaker_map[line.speaker_name] = speaker.id

                    line.speaker_id = speaker_map[line.speaker_name]
                    final_lines.append(line)

                await repo.add_lines(final_lines)
                await session.commit()
            except Exception:
                await session.rollback()
                raise

        await update_progress(100)
