"""Which files are audio tracks. See docs/audio-sources.md."""

from pathlib import PurePath

AUDIO_EXTENSIONS = [
    "mp3",
    "wav",
    "m4a",
    "m4b",
    "mp4",
    "flac",
    "ogg",
    "opus",
    "webm",
    "aac",
    "aif",
    "aiff",
    "wma",
]
"""What counts as an audio track: the picker offers these, imports accept only these, and
``sources/`` is filtered by them. ``mp4`` and ``webm`` are video containers that usually
carry the audio of a recorded call; transcription reads their sound track."""


class UnsupportedAudioError(ValueError):
    """A file offered as a track is not one Chronicler reads as audio."""


def is_audio_track(name: str) -> bool:
    """Whether a file called `name` in ``sources/`` is a track: audio, and not hidden."""
    path = PurePath(name)
    return not path.name.startswith(".") and path.suffix[1:].lower() in AUDIO_EXTENSIONS


def require_audio_track(name: str) -> None:
    """Refuses a name that would land in ``sources/`` and never be listed as a track."""
    if not is_audio_track(name):
        supported = ", ".join(AUDIO_EXTENSIONS)
        raise UnsupportedAudioError(
            f"{PurePath(name).name} is not an audio file Chronicler can use. "
            f"Supported formats: {supported}."
        )
