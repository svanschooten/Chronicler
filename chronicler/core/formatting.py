"""
Shared time formatting - used by chronicle duration display, the transcript view's per-line
timestamp toggle, timestamped export, and timestamped import, so a timestamp reads the same
everywhere in the app instead of each call site inventing its own convention.
"""

from chronicler.core.models import TranscriptLine


def format_duration(seconds: float) -> str:
    """A short, human-friendly duration for Chronicle.duration - "1h 24m", "45m 12s", "12s"."""
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def format_timestamp(seconds: float, include_millis: bool = False) -> str:
    """
    A fixed-width "HH:MM:SS" clock timestamp for a single transcript line - unlike
    format_duration, always zero-padded so a column of these lines up.
    """
    total_ms = max(0, int(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return (
        f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
        if include_millis
        else f"{hours:02d}:{minutes:02d}:{secs:02d}"
    )


def parse_timestamp(text: str) -> float:
    """
    The inverse of format_timestamp, but also accepts "MM:SS" (no hours) and a fractional-
    seconds suffix (".5"), since that's a common way for a hand-edited or tool-exported
    transcript to write a timestamp.
    """
    text = text.strip()
    frac = 0.0
    if "." in text:
        text, frac_part = text.split(".", 1)
        if not frac_part.isdigit():
            raise ValueError(f"Unrecognized timestamp format: {text!r}")
        frac = float(f"0.{frac_part}")

    parts = text.split(":")
    if not all(p.isdigit() for p in parts):
        raise ValueError(f"Unrecognized timestamp format: {text!r}")

    if len(parts) == 3:
        hours, minutes, secs = (int(p) for p in parts)
    elif len(parts) == 2:
        hours = 0
        minutes, secs = (int(p) for p in parts)
    else:
        raise ValueError(f"Unrecognized timestamp format: {text!r}")

    return hours * 3600 + minutes * 60 + secs + frac


class NoRealTimestampsError(ValueError):
    """Raised when a transcript's timings are synthetic line indices rather than seconds."""


def looks_synthetic(lines: list[TranscriptLine]) -> bool:
    """
    True when the timings are line indices rather than seconds.

    Lines carry a `synthetic_timing` flag, written by the importer and the transcriber and
    kept through cleaning. Older rows have none, so when no line has a flag the fallback
    applies: two or more lines whose start and end times are all whole numbers.
    """
    flags = [line.synthetic_timing for line in lines]
    if any(flag is not None for flag in flags):
        return all(flag is not False for flag in flags)
    if len(lines) < 2:
        return False
    return all(line.start_time.is_integer() and line.end_time.is_integer() for line in lines)
