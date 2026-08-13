import asyncio
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.formatting import format_duration
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
            timestamp_group = data.get("timestamp_group")
            importer = RegexImporter(regex, speaker_group, text_group, timestamp_group)
        else:
            importer = DefaultImporter()

        lines = importer.parse(content)
        logger.info(f"Parsed {len(lines)} lines from {file_path}")

        await update_progress(50)

        # When appending, existing lines stay - only the new ones need to be ordered
        # after them. get_lines() orders by start_time, and RegexImporter now emits
        # sequential 0-based start_time per file (see importers.py), so every append
        # needs its own lines shifted past whatever's already there.
        append = bool(data.get("append"))

        session = await self.db_manager.get_project_session(
            str(task.chronicle_id), custom_path=custom_path
        )
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

                # Not len(speaker_map): in append mode that only counts speakers in
                # the *new* file, undercounting a chronicle that already had others.
                # Counting distinct names across every line now in the transcript is
                # correct in both modes.
                final_speaker_count = len(
                    {line.speaker_name for line in await repo.get_lines()}
                )
            except Exception:
                await session.rollback()
                raise

        if self.chronicle_repo:
            await self.chronicle_repo.add_tag(task.chronicle_id, "Transcript")
        await self._backfill_speakers_count(task.chronicle_id, final_speaker_count)

        await update_progress(100)
        logger.info(
            f"Transcript import finished for chronicle {task.chronicle_id}: "
            f"{len(final_lines)} lines, {final_speaker_count} speakers"
        )

    async def _backfill_speakers_count(self, chronicle_id, count: int) -> None:
        # RegexImporter/TranscriptCleaner already produce a full speaker_map as a
        # side effect of parsing - this is free, not a separate "identify speakers"
        # pass, so it always runs rather than needing an opt-in. See also
        # TranscriptService.refresh_speaker_count for the manual reconciliation path
        # (edited transcripts, or chronicles imported before this existed).
        if not self.chronicle_repo:
            return
        chronicle = await self.chronicle_repo.get_by_id(chronicle_id)
        if chronicle and chronicle.speakers_count != count:
            chronicle.speakers_count = count
            await self.chronicle_repo.update(chronicle)

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
                logger.info(f"Cleaning {len(lines)} lines for chronicle {task.chronicle_id}")

                await update_progress(30)

                cleaner = TranscriptCleaner()
                cleaned_lines = cleaner.clean(lines)
                logger.info(f"Cleaned down to {len(cleaned_lines)} lines")

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

        await self._backfill_speakers_count(task.chronicle_id, len(speaker_map))

        await update_progress(100)
        logger.info(
            f"Transcript clean finished for chronicle {task.chronicle_id}: "
            f"{len(final_lines)} lines, {len(speaker_map)} speakers"
        )

    async def handle_transcribe(self, task: Task, update_progress: Callable[[int], Any]):
        if not task.chronicle_id:
            raise ValueError("Task has no chronicle_id")

        data = json.loads(task.data) if task.data else {}
        file_path = data.get("file_path")
        if not file_path:
            raise ValueError("No file_path provided for transcribe task")
        speaker_name = data.get("speaker_name")
        if not speaker_name:
            raise ValueError("No speaker_name provided for transcribe task")

        # The file was already moved into the chronicle's durable sources/ directory
        # by ChronicleService.add_audio_source when it was imported - a separate,
        # earlier step from transcribing it (see TODO.md). Confined to that directory
        # specifically, not the shared imports/ scratch space handle_import uses.
        resolved_path = Path(file_path).resolve()
        sources_root = self.db_manager.get_chronicle_sources_path(
            str(task.chronicle_id)
        ).resolve()
        if not resolved_path.is_relative_to(sources_root):
            raise ValueError(
                f"file_path must be inside the chronicle's sources directory: {file_path}"
            )

        logger.info(
            f"Transcribing audio {file_path} for chronicle {task.chronicle_id} "
            f"(speaker: {speaker_name})"
        )

        custom_path = None
        if self.chronicle_repo:
            chronicle = await self.chronicle_repo.get_by_id(task.chronicle_id)
            if chronicle and chronicle.project_path:
                custom_path = Path(chronicle.project_path)

        await update_progress(10)

        try:
            from chronicler.core.processing.transcriber import transcribe_audio
        except ImportError as ex:
            raise RuntimeError(
                "Audio transcription requires the 'transcription' extra "
                "(pip install 'chronicler[transcription]')"
            ) from ex

        # transcribe_audio is synchronous and CPU-bound (potentially minutes for a
        # long recording) - run it off the event loop, which in desktop full-stack
        # mode is shared with the UI itself.
        lines = await asyncio.to_thread(transcribe_audio, str(resolved_path))
        logger.info(f"Transcribed {len(lines)} segments from {resolved_path.name}")

        await update_progress(70)

        # No offsetting of start_time/end_time (contrast with handle_import's append
        # mode): each audio source is one participant's own track from the same
        # Discord recording session, already time-aligned with every other track -
        # the raw per-segment seconds are real, shared-timeline positions, so sorting
        # the combined transcript by start_time interleaves speakers correctly.
        session = await self.db_manager.get_project_session(
            str(task.chronicle_id), custom_path=custom_path
        )
        async with session:
            repo = SQLiteTranscriptRepository(session)
            try:
                # One audio source = one speaker's track (see queue_transcribe) - only
                # that speaker's previous lines are replaced, not the whole
                # transcript, so other speakers' already-transcribed tracks survive.
                speaker = await repo.get_or_create_speaker(speaker_name)
                await repo.delete_lines_by_speaker(speaker.id)
                for line in lines:
                    line.speaker_id = speaker.id
                    line.speaker_name = speaker_name
                await repo.add_lines(lines)
                await session.commit()

                # One fetch, reused for speaker count and duration below: both are
                # derived from the *whole* transcript (every speaker's track), not
                # just the one just transcribed.
                all_lines = await repo.get_lines()
                final_speaker_count = len({line.speaker_name for line in all_lines})
                total_duration_seconds = max(
                    (line.end_time for line in all_lines), default=0.0
                )
            except Exception:
                await session.rollback()
                raise

        if self.chronicle_repo:
            await self.chronicle_repo.add_tag(task.chronicle_id, "Transcript")
        await self._backfill_transcribe_metadata(
            task.chronicle_id, final_speaker_count, total_duration_seconds
        )

        await update_progress(100)
        logger.info(
            f"Transcription finished for chronicle {task.chronicle_id}: "
            f"{len(lines)} segments for speaker '{speaker_name}'"
        )

    async def _backfill_transcribe_metadata(
        self, chronicle_id, speakers_count: int, duration_seconds: float
    ) -> None:
        # Real segment timestamps only exist after transcribing audio - text
        # imports/cleans use synthetic per-line indices as start_time/end_time (see
        # importers.py), which would produce a meaningless "duration". So duration is
        # only ever backfilled here, not in handle_import/handle_clean.
        if not self.chronicle_repo:
            return
        chronicle = await self.chronicle_repo.get_by_id(chronicle_id)
        if not chronicle:
            return

        changed = False
        if chronicle.speakers_count != speakers_count:
            chronicle.speakers_count = speakers_count
            changed = True

        duration_str = format_duration(duration_seconds)
        if chronicle.duration != duration_str:
            chronicle.duration = duration_str
            changed = True

        # "Imported" is the model default, not something a text import ever sets
        # deliberately - only overridden here if it's still that default, so a
        # chronicle that was already explicitly something else (e.g. re-transcribing
        # a second speaker's track after the first) doesn't get stomped back.
        if chronicle.status == "Imported":
            chronicle.status = "Transcribed"
            changed = True

        if changed:
            await self.chronicle_repo.update(chronicle)
