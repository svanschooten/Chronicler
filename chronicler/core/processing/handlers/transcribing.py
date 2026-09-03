"""
The TRANSCRIBE task handler - turn one imported audio track into transcript lines for the
speaker it belongs to.
"""

import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID

from chronicler.core.config_sections import AUTO_LANGUAGE
from chronicler.core.formatting import format_duration
from chronicler.core.models import Task
from chronicler.core.processing.fingerprint import fingerprint_file
from chronicler.core.processing.handlers.base import ProgressCallback
from chronicler.core.processing.handlers.normalizing import NormalizeHandler
from chronicler.core.sqlite import SQLiteAudioSourceRepository, SQLiteTranscriptRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TranscriptionParameters:
    """The values one transcribe run will actually use."""

    language: str | None
    no_speech_threshold: float
    model_size: str
    device: str
    compute_type: str


class TranscribeHandler(NormalizeHandler):
    def transcription_parameters(self, task: Task) -> TranscriptionParameters:
        """Task payload values where present, configured defaults everywhere else."""
        data = self.task_data(task)
        defaults = self.settings.transcription

        language = data.get("language", defaults.language)
        if language == AUTO_LANGUAGE:
            language = None

        return TranscriptionParameters(
            language=language,
            no_speech_threshold=data.get("no_speech_threshold", defaults.no_speech_threshold),
            model_size=data.get("model_size", defaults.model_size),
            device=defaults.device,
            compute_type=defaults.compute_type,
        )

    async def handle_transcribe(self, task: Task, update_progress: ProgressCallback):
        chronicle_id = self.require_chronicle_id(task)
        data = self.task_data(task)
        file_path = self.require_field(data, "file_path", "transcribe")
        speaker_name = self.require_field(data, "speaker_name", "transcribe")
        parameters = self.transcription_parameters(task)

        resolved_path = self.confine_to(
            file_path,
            self.db_manager.get_chronicle_sources_path(str(chronicle_id)),
            "the chronicle's sources directory",
        )

        logger.info(
            f"Transcribing audio {file_path} for chronicle {chronicle_id} "
            f"(speaker: {speaker_name}, language: {parameters.language or AUTO_LANGUAGE}, "
            f"model: {parameters.model_size})"
        )

        await self._register_source(chronicle_id, resolved_path.name, speaker_name)
        await update_progress(10)

        normalize_first = data.get("normalize_first", self.settings.transcription.normalize_first)
        if normalize_first:
            try:
                await self.ensure_normalized(chronicle_id, resolved_path)
            except Exception as error:
                logger.warning(f"Could not normalize {resolved_path.name}: {error}")

        audio_path = await self.transcription_source(chronicle_id, resolved_path)
        if audio_path != resolved_path:
            logger.info(f"Transcribing the normalized copy {audio_path.name}")
        await update_progress(30)

        try:
            lines = await self._transcribe(str(audio_path), speaker_name, parameters)
        except Exception as error:
            await self._record_failure(chronicle_id, resolved_path.name, str(error))
            raise
        logger.info(f"Transcribed {len(lines)} segments from {resolved_path.name}")

        await update_progress(70)

        session = await self.project_session(chronicle_id)
        async with session:
            repo = SQLiteTranscriptRepository(session)
            sources = SQLiteAudioSourceRepository(session)
            try:
                speaker = await repo.get_or_create_speaker(speaker_name)
                await repo.delete_lines_by_speaker(speaker.id)

                await self.attach_speakers(repo, lines)
                await repo.add_lines(lines)

                await sources.register(
                    resolved_path.name,
                    content_hash=fingerprint_file(resolved_path),
                    size_bytes=resolved_path.stat().st_size,
                )
                await sources.set_speaker(resolved_path.name, speaker.id)
                await sources.mark_transcribed(
                    resolved_path.name,
                    content_hash=fingerprint_file(resolved_path),
                    language=parameters.language,
                    model=parameters.model_size,
                )
                await session.commit()

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

    async def _register_source(self, chronicle_id: UUID, filename: str, speaker_name: str) -> None:
        path = self.db_manager.get_chronicle_sources_path(str(chronicle_id)) / filename
        session = await self.project_session(chronicle_id)
        async with session:
            sources = SQLiteAudioSourceRepository(session)
            await sources.register(
                filename,
                content_hash=fingerprint_file(path) if path.exists() else None,
                size_bytes=path.stat().st_size if path.exists() else None,
            )
            await sources.mark_transcribing(filename)
            await session.commit()

    async def _record_failure(self, chronicle_id: UUID, filename: str, error: str) -> None:
        session = await self.project_session(chronicle_id)
        async with session:
            try:
                await SQLiteAudioSourceRepository(session).mark_transcription_failed(
                    filename, error
                )
                await session.commit()
            except KeyError:
                await session.rollback()

    @staticmethod
    async def _transcribe(path: str, speaker_name: str, parameters: TranscriptionParameters):
        """
        The ImportError guard wraps the call, not the import: faster-whisper is imported
        lazily inside the transcriber, so a missing extra only surfaces once a model is
        actually built.
        """
        try:
            from chronicler.core.processing import transcriber

            return await asyncio.to_thread(
                lambda: transcriber.transcribe_audio(
                    path,
                    speaker_name,
                    language=parameters.language,
                    no_speech_threshold=parameters.no_speech_threshold,
                    model_size=parameters.model_size,
                    device=parameters.device,
                    compute_type=parameters.compute_type,
                )
            )
        except ImportError as ex:
            raise RuntimeError(
                "Audio transcription requires the 'transcription' extra "
                "(pip install 'chronicler[transcription]')"
            ) from ex

    async def _backfill_metadata(
        self, chronicle_id: UUID, speakers_count: int, duration_seconds: float
    ) -> None:
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

        if chronicle.status == "Imported":
            chronicle.status = "Transcribed"
            changed = True

        if changed:
            await self.chronicle_repo.update(chronicle)
