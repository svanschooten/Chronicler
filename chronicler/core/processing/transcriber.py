import logging
from typing import TYPE_CHECKING, Any

from chronicler.core.models import TranscriptLine

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# "base" balances download size (~150MB) against accuracy for a local-first desktop
# app that can't assume a GPU. Not exposed as a Settings field yet - nobody's asked
# to tune it, and it's one constant to change here when someone does.
DEFAULT_MODEL_SIZE = "base"

# Keyed by model_size: constructing WhisperModel is what triggers the (possibly
# multi-hundred-MB) download from HuggingFace Hub on first use, so it's cached here
# rather than reloaded per task.
_model_cache: dict[str, Any] = {}


def _get_model(model_size: str) -> Any:
    # Imported lazily, inside this function, not at module level: importing
    # transcriber.py (e.g. because WorkerHandlers imports it) must not require
    # faster-whisper to be installed, and must never trigger a model download just
    # by being imported - only an actual transcribe_audio() call should do that.
    from faster_whisper import WhisperModel

    if model_size not in _model_cache:
        logger.info(f"Loading faster-whisper model '{model_size}' (downloads on first use)")
        _model_cache[model_size] = WhisperModel(model_size, device="cpu", compute_type="int8")
    return _model_cache[model_size]


def transcribe_audio(
    file_path: str, speaker_name: str, model_size: str = DEFAULT_MODEL_SIZE
) -> list[TranscriptLine]:
    """Synchronous and CPU-bound - callers on an event loop (see
    WorkerHandlers.handle_transcribe) must run this via asyncio.to_thread(), not
    await it directly, or a long transcription blocks everything else sharing that
    loop (the desktop UI, in full-stack mode).

    faster-whisper doesn't diarize, so every segment in one file belongs to the same
    speaker - `speaker_name` says which, since one audio source is one participant's
    own track and the caller already knows whose. Splitting a mixed recording into
    per-speaker segments is future work (see TODO.md); until then this parameter is
    what makes the output correctly attributed rather than generically labelled.
    """
    model = _get_model(model_size)
    segments, _info = model.transcribe(file_path)

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
