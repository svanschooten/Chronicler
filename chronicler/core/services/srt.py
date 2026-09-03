"""SubRip (.srt) rendering for a transcript."""

from chronicler.core.models import TranscriptLine

MINIMUM_CUE_SECONDS = 0.5


class NoRealTimestampsError(ValueError):
    """Raised when a transcript's timings are synthetic line indices rather than seconds."""


def srt_timestamp(seconds: float) -> str:
    """`HH:MM:SS,mmm`, truncating rather than rounding so a cue never gains a second."""
    total_ms = max(0, int(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def looks_synthetic(lines: list[TranscriptLine]) -> bool:
    """
    True when every line starts one second after the last, which is what the text importer
    writes when a source carries no timings of its own.
    """
    if len(lines) < 2:
        return False
    return all(
        line.start_time == float(index) and line.end_time == float(index + 1)
        for index, line in enumerate(lines)
    )


def format_srt(
    lines: list[TranscriptLine],
    include_speaker: bool = True,
    require_real_timestamps: bool = False,
) -> str:
    if require_real_timestamps and looks_synthetic(lines):
        raise NoRealTimestampsError(
            "This transcript has no real timestamps - it was imported from text, where each "
            "line is numbered rather than timed. Subtitles need timings from transcribed audio."
        )

    cues: list[str] = []
    for line in lines:
        text = line.text.strip()
        if not text:
            continue

        end = line.end_time
        if end <= line.start_time:
            end = line.start_time + MINIMUM_CUE_SECONDS

        body = f"{line.speaker_name or 'Unknown'}: {text}" if include_speaker else text
        cues.append(
            f"{len(cues) + 1}\n{srt_timestamp(line.start_time)} --> {srt_timestamp(end)}\n{body}\n"
        )

    return "\n".join(cues)
