import json
import logging
from collections.abc import Callable
from typing import Any

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import Task
from chronicler.core.processing.cleaners import TranscriptCleaner
from chronicler.core.processing.importers import DefaultImporter
from chronicler.core.sqlite_repository import SQLiteTranscriptRepository

logger = logging.getLogger(__name__)


class WorkerHandlers:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    async def handle_import(self, task: Task, update_progress: Callable[[int], Any]):
        if not task.chronicle_id:
            raise ValueError("Task has no chronicle_id")

        data = json.loads(task.data) if task.data else {}
        file_path = data.get("file_path")
        if not file_path:
            raise ValueError("No file_path provided for import task")

        logger.info(f"Importing transcript from {file_path} for chronicle {task.chronicle_id}")

        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        importer = DefaultImporter()
        lines = importer.parse(content)

        await update_progress(50)

        session = await self.db_manager.get_project_session(str(task.chronicle_id))
        async with session:
            repo = SQLiteTranscriptRepository(session)
            await repo.delete_all()

            final_lines = []
            speaker_map = {}
            for line in lines:
                if line.speaker_name not in speaker_map:
                    speaker = await repo.get_or_create_speaker(line.speaker_name)
                    speaker_map[line.speaker_name] = speaker.id

                line.speaker_id = speaker_map[line.speaker_name]
                final_lines.append(line)

            await repo.add_lines(final_lines)

        await update_progress(100)

    async def handle_clean(self, task: Task, update_progress: Callable[[int], Any]):
        if not task.chronicle_id:
            raise ValueError("Task has no chronicle_id")

        logger.info(f"Cleaning transcript for chronicle {task.chronicle_id}")

        session = await self.db_manager.get_project_session(str(task.chronicle_id))
        async with session:
            repo = SQLiteTranscriptRepository(session)
            lines = await repo.get_lines()

            await update_progress(30)

            cleaner = TranscriptCleaner()
            cleaned_lines = cleaner.clean(lines)

            await update_progress(70)

            await repo.delete_all()

            final_lines = []
            speaker_map = {}
            for line in cleaned_lines:
                if line.speaker_name not in speaker_map:
                    speaker = await repo.get_or_create_speaker(line.speaker_name)
                    speaker_map[line.speaker_name] = speaker.id

                line.speaker_id = speaker_map[line.speaker_name]
                final_lines.append(line)

            await repo.add_lines(final_lines)

        await update_progress(100)
