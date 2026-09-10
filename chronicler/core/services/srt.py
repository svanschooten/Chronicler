"""SubRip (.srt) rendering for a transcript."""

from chronicler.core.formatting import NoRealTimestampsError, format_timestamp, looks_synthetic
from chronicler.core.models import TranscriptLine

MINIMUM_CUE_SECONDS = 0.5


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
            f"{len(cues) + 1}\n{format_timestamp(line.start_time, True)} "
            + f"--> {format_timestamp(end, True)}\n{body}\n"
        )

    return "\n".join(cues)
