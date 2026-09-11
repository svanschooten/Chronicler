"""Tests for the NORMALIZE task handler."""

import json
import math
import wave
from unittest.mock import patch
from uuid import uuid4

import pytest

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import Task, TaskType
from chronicler.core.processing.handlers import WorkerHandlers
from chronicler.core.processing.normalizer import NORMALIZED_SUFFIX, NormalizationError
from chronicler.core.sqlite import SQLiteAudioSourceRepository

pytest.importorskip("av", reason="requires the 'normalization' extra", exc_type=ImportError)


@pytest.fixture(autouse=True)
def _defaults_not_the_developers_config(isolated_config):
    """
    `Settings()` here has to mean the shipped defaults.

    Without this it reads whatever is in ~/.config/Chronicler, so a machine with a real
    language model configured ran these against it - one of them over the network. See
    docs/testing.md.
    """


async def _noop_progress(_progress: int) -> None:
    pass


def write_tone(path, seconds=1.0, amplitude=0.03, rate=16000):
    frames = bytearray()
    for index in range(int(seconds * rate)):
        value = int(amplitude * 32767 * math.sin(2 * math.pi * 440 * index / rate))
        frames += int(value).to_bytes(2, "little", signed=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(bytes(frames))
    return path


async def _fixture(tmp_path, settings=None):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    handlers = WorkerHandlers(db_manager, settings=settings)
    chronicle_id = uuid4()
    sources = db_manager.get_chronicle_sources_path(str(chronicle_id))
    audio = write_tone(sources / "gm.wav")
    return db_manager, handlers, chronicle_id, audio


def _task(chronicle_id, audio):
    return Task(
        type=TaskType.NORMALIZE,
        chronicle_id=chronicle_id,
        data=json.dumps({"file_path": str(audio)}),
    )


async def _record(db_manager, chronicle_id, filename="gm.wav"):
    session = await db_manager.get_project_session(str(chronicle_id))
    async with session:
        return await SQLiteAudioSourceRepository(session).get_by_filename(filename)


class TestHandleNormalize:
    @pytest.mark.asyncio
    async def test_writes_a_normalized_sibling_and_keeps_the_original(self, tmp_path):
        db_manager, handlers, chronicle_id, audio = await _fixture(tmp_path)
        try:
            before = audio.read_bytes()

            await handlers.handle_normalize(_task(chronicle_id, audio), _noop_progress)

            assert (audio.parent / f"gm{NORMALIZED_SUFFIX}").exists()
            assert audio.read_bytes() == before
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_records_the_state_on_the_source(self, tmp_path):
        db_manager, handlers, chronicle_id, audio = await _fixture(tmp_path)
        try:
            await handlers.handle_normalize(_task(chronicle_id, audio), _noop_progress)

            record = await _record(db_manager, chronicle_id)
            assert record.normalization_state.value == "DONE"
            assert record.is_normalized is True
            assert record.normalized_filename == f"gm{NORMALIZED_SUFFIX}"
            assert record.loudness_before is not None
            assert record.loudness_after is not None
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_a_second_run_is_skipped(self, tmp_path):
        db_manager, handlers, chronicle_id, audio = await _fixture(tmp_path)
        try:
            await handlers.handle_normalize(_task(chronicle_id, audio), _noop_progress)

            with patch("chronicler.core.processing.normalizer.normalize_audio") as normalize:
                await handlers.handle_normalize(_task(chronicle_id, audio), _noop_progress)

            normalize.assert_not_called()
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_force_reruns_a_completed_source(self, tmp_path):
        db_manager, handlers, chronicle_id, audio = await _fixture(tmp_path)
        try:
            await handlers.handle_normalize(_task(chronicle_id, audio), _noop_progress)

            task = _task(chronicle_id, audio)
            task.data = json.dumps({"file_path": str(audio), "force": True})
            await handlers.handle_normalize(task, _noop_progress)

            record = await _record(db_manager, chronicle_id)
            assert record.is_normalized is True
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_replacing_the_source_makes_it_normalizable_again(self, tmp_path):
        db_manager, handlers, chronicle_id, audio = await _fixture(tmp_path)
        try:
            await handlers.handle_normalize(_task(chronicle_id, audio), _noop_progress)
            write_tone(audio, seconds=2.0, amplitude=0.01)

            record = await _record(db_manager, chronicle_id)
            assert record.is_normalized is True

            session = await db_manager.get_project_session(str(chronicle_id))
            async with session:
                repo = SQLiteAudioSourceRepository(session)
                from chronicler.core.processing.fingerprint import fingerprint_file

                await repo.register("gm.wav", content_hash=fingerprint_file(audio))
                await session.commit()

            stale = await _record(db_manager, chronicle_id)
            assert stale.is_normalized is False
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_a_failure_is_recorded_and_raised(self, tmp_path):
        db_manager, handlers, chronicle_id, audio = await _fixture(tmp_path)
        try:
            with patch(
                "chronicler.core.processing.normalizer.normalize_audio",
                side_effect=NormalizationError("no audio stream"),
            ):
                with pytest.raises(NormalizationError):
                    await handlers.handle_normalize(_task(chronicle_id, audio), _noop_progress)

            record = await _record(db_manager, chronicle_id)
            assert record.normalization_state.value == "FAILED"
            assert "no audio stream" in record.normalization_error
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_a_path_outside_the_sources_directory_is_refused(self, tmp_path):
        db_manager, handlers, chronicle_id, _ = await _fixture(tmp_path)
        try:
            outside = tmp_path / "elsewhere.wav"
            write_tone(outside)
            task = Task(
                type=TaskType.NORMALIZE,
                chronicle_id=chronicle_id,
                data=json.dumps({"file_path": str(outside)}),
            )

            with pytest.raises(ValueError, match="sources directory"):
                await handlers.handle_normalize(task, _noop_progress)
        finally:
            await db_manager.close_all()


class TestNormalizeBeforeTranscribe:
    @pytest.mark.asyncio
    async def test_transcription_uses_the_normalized_file_when_one_exists(self, tmp_path):
        db_manager, handlers, chronicle_id, audio = await _fixture(tmp_path)
        try:
            await handlers.handle_normalize(_task(chronicle_id, audio), _noop_progress)

            captured = {}

            def fake(path, speaker, **kwargs):
                captured["path"] = path
                return []

            with patch("chronicler.core.processing.transcriber.transcribe_audio", side_effect=fake):
                await handlers.handle_transcribe(
                    Task(
                        type=TaskType.TRANSCRIBE,
                        chronicle_id=chronicle_id,
                        data=json.dumps({"file_path": str(audio), "speaker_name": "GM"}),
                    ),
                    _noop_progress,
                )

            assert captured["path"].endswith(NORMALIZED_SUFFIX)
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_transcription_uses_the_raw_file_when_not_normalized(self, tmp_path):
        db_manager, handlers, chronicle_id, audio = await _fixture(tmp_path)
        try:
            captured = {}

            def fake(path, speaker, **kwargs):
                captured["path"] = path
                return []

            with patch("chronicler.core.processing.transcriber.transcribe_audio", side_effect=fake):
                await handlers.handle_transcribe(
                    Task(
                        type=TaskType.TRANSCRIBE,
                        chronicle_id=chronicle_id,
                        data=json.dumps({"file_path": str(audio), "speaker_name": "GM"}),
                    ),
                    _noop_progress,
                )

            assert captured["path"] == str(audio)
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_normalize_first_normalizes_then_transcribes_the_result(self, tmp_path):
        db_manager, handlers, chronicle_id, audio = await _fixture(tmp_path)
        try:
            captured = {}

            def fake(path, speaker, **kwargs):
                captured["path"] = path
                return []

            with patch("chronicler.core.processing.transcriber.transcribe_audio", side_effect=fake):
                await handlers.handle_transcribe(
                    Task(
                        type=TaskType.TRANSCRIBE,
                        chronicle_id=chronicle_id,
                        data=json.dumps(
                            {
                                "file_path": str(audio),
                                "speaker_name": "GM",
                                "normalize_first": True,
                            }
                        ),
                    ),
                    _noop_progress,
                )

            assert captured["path"].endswith(NORMALIZED_SUFFIX)
            record = await _record(db_manager, chronicle_id)
            assert record.is_normalized is True
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_normalize_first_from_settings_applies_without_a_task_flag(self, tmp_path):
        from chronicler.core.config import Settings

        settings = Settings()
        settings.transcription.normalize_first = True
        db_manager, handlers, chronicle_id, audio = await _fixture(tmp_path, settings)
        try:
            captured = {}

            def fake(path, speaker, **kwargs):
                captured["path"] = path
                return []

            with patch("chronicler.core.processing.transcriber.transcribe_audio", side_effect=fake):
                await handlers.handle_transcribe(
                    Task(
                        type=TaskType.TRANSCRIBE,
                        chronicle_id=chronicle_id,
                        data=json.dumps({"file_path": str(audio), "speaker_name": "GM"}),
                    ),
                    _noop_progress,
                )

            assert captured["path"].endswith(NORMALIZED_SUFFIX)
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_normalize_first_skips_an_already_normalized_source(self, tmp_path):
        db_manager, handlers, chronicle_id, audio = await _fixture(tmp_path)
        try:
            await handlers.handle_normalize(_task(chronicle_id, audio), _noop_progress)

            with (
                patch("chronicler.core.processing.normalizer.normalize_audio") as normalize,
                patch("chronicler.core.processing.transcriber.transcribe_audio", return_value=[]),
            ):
                await handlers.handle_transcribe(
                    Task(
                        type=TaskType.TRANSCRIBE,
                        chronicle_id=chronicle_id,
                        data=json.dumps(
                            {
                                "file_path": str(audio),
                                "speaker_name": "GM",
                                "normalize_first": True,
                            }
                        ),
                    ),
                    _noop_progress,
                )

            normalize.assert_not_called()
        finally:
            await db_manager.close_all()
