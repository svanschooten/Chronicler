import logging
from typing import Any

from chronicler.core.config_sections import AUTO_LANGUAGE, TranscriptionSettings
from chronicler.core.models import TranscriptLine

logger = logging.getLogger(__name__)

_model_cache: dict[tuple[str, str, str], Any] = {}


def _get_model(model_size: str, device: str, compute_type: str) -> Any:
    from faster_whisper import WhisperModel

    key = (model_size, device, compute_type)
    if key not in _model_cache:
        logger.info(f"Loading faster-whisper model '{model_size}' (downloads on first use)")
        _model_cache[key] = WhisperModel(model_size, device=device, compute_type=compute_type)
    return _model_cache[key]


def transcribe_audio(
    file_path: str,
    speaker_name: str,
    language: str | None = None,
    no_speech_threshold: float | None = None,
    model_size: str | None = None,
    device: str | None = None,
    compute_type: str | None = None,
    settings: TranscriptionSettings | None = None,
) -> list[TranscriptLine]:
    """Transcribes one single-speaker track, defaulting every parameter from settings."""
    defaults = settings or TranscriptionSettings()

    resolved_language = language if language is not None else defaults.language
    if resolved_language == AUTO_LANGUAGE:
        resolved_language = None

    model = _get_model(
        model_size or defaults.model_size,
        device or defaults.device,
        compute_type or defaults.compute_type,
    )
    segments, _info = model.transcribe(
        file_path,
        language=resolved_language,
        no_speech_threshold=(
            no_speech_threshold if no_speech_threshold is not None else defaults.no_speech_threshold
        ),
    )

    lines = []
    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        lines.append(
            TranscriptLine(
                speaker_name=speaker_name,
                text=text,
                start_time=segment.start,
                end_time=segment.end,
            )
        )
    return lines
