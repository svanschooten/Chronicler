"""The TRANSCRIBE task handler - turn one imported audio track into transcript lines
for the speaker it belongs to."""

import asyncio
import logging
from uuid import UUID

from chronicler.core.formatting import format_duration
from chronicler.core.models import Task
from chronicler.core.processing.handlers.base import HandlerBase, ProgressCallback
from chronicler.core.sqlite import SQLiteTranscriptRepository

logger = logging.getLogger(__name__)


class TranscribeHandler(HandlerBase):
    async def handle_transcribe(self, task: Task, update_progress: ProgressCallback):
        chronicle_id = self.require_chronicle_id(task)
        data = self.task_data(task)
        file_path = self.require_field(data, "file_path", "transcribe")
        speaker_name = self.require_field(data, "speaker_name", "transcribe")

        # The file was already moved into the chronicle's durable sources/ directory by
        # ChronicleService.add_audio_source when it was imported - a separate, earlier
        # step from transcribing it. Confined to that directory specifically, not the
        # shared imports/ scratch space the import handler uses.
        resolved_path = self.confine_to(
            file_path,
            self.db_manager.get_chronicle_sources_path(str(chronicle_id)),
            "the chronicle's sources directory",
        )

        logger.info(
            f"Transcribing audio {file_path} for chronicle {chronicle_id} (speaker: {speaker_name})"
        )

        await update_progress(10)

        lines = await self._transcribe(str(resolved_path), speaker_name)
        logger.info(f"Transcribed {len(lines)} segments from {resolved_path.name}")

        await update_progress(70)

        # No offsetting of start_time/end_time (contrast with the import handler's
        # append mode): each audio source is one participant's own track from the same
        # recording session, already time-aligned with every other track - the raw
        # per-segment seconds are real, shared-timeline positions, so sorting the
        # combined transcript by start_time interleaves speakers correctly.
        session = await self.project_session(chronicle_id)
        async with session:
            repo = SQLiteTranscriptRepository(session)
            try:
                # One audio source = one speaker's track (see queue_transcribe) - only
                # that speaker's previous lines are replaced, not the whole transcript,
                # so other speakers' already-transcribed tracks survive. Resolved here
                # rather than from the transcribed lines because the replacement has to
                # happen even when the track turned out to be silent.
                speaker = await repo.get_or_create_speaker(speaker_name)
                await repo.delete_lines_by_speaker(speaker.id)

                # The lines already carry the right speaker_name - _transcribe was told
                # whose track this is. All that's left is the speaker row's id, which
                # only the database can supply.
                await self.attach_speakers(repo, lines)
                await repo.add_lines(lines)
                await session.commit()

                # One fetch, reused for speaker count and duration below: both are
                # derived from the *whole* transcript (every speaker's track), not just
                # the one just transcribed.
                all_lines = await repo.get_lines()
                final_speaker_count = len({line.speaker_name for line in all_lines})
                total_duration_seconds = max((line.end_time for line in all_lines), default=0.0)
            except Exception:
                await session.rollback()
                raise

        await self.tag_as_transcript(chronicle_id)
        await self._backfill_metadata(chronicle_id, final_speaker_count, total_duration_seconds)

        await update_progress(100)
        logger.info(
            f"Transcription finished for chronicle {chronicle_id}: "
            f"{len(lines)} segments for speaker '{speaker_name}'"
        )

    @staticmethod
    async def _transcribe(path: str, speaker_name: str):
        # Imported lazily so the whole app doesn't require the optional
        # 'transcription' extra just to start, and so the (large) model is only ever
        # downloaded on first real use.
        try:
            from chronicler.core.processing.transcriber import transcribe_audio
        except ImportError as ex:
            raise RuntimeError(
                "Audio transcription requires the 'transcription' extra "
                "(pip install 'chronicler[transcription]')"
            ) from ex

        # transcribe_audio is synchronous and CPU-bound (potentially minutes for a long
        # recording) - run it off the event loop, which in desktop full-stack mode is
        # shared with the UI itself.
        return await asyncio.to_thread(transcribe_audio, path, speaker_name)

    async def _backfill_metadata(
        self, chronicle_id: UUID, speakers_count: int, duration_seconds: float
    ) -> None:
        # Real segment timestamps only exist after transcribing audio - text
        # imports/cleans use synthetic per-line indices as start_time/end_time (see
        # importers.py), which would produce a meaningless "duration". So duration is
        # only ever backfilled here, not by the import or clean handlers.
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
        # chronicle that was already explicitly something else (e.g. re-transcribing a
        # second speaker's track after the first) doesn't get stomped back.
        if chronicle.status == "Imported":
            chronicle.status = "Transcribed"
            changed = True

        if changed:
            await self.chronicle_repo.update(chronicle)
