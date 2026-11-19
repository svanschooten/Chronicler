"""Plain-text (.txt) rendering for a transcript."""

import textwrap

from chronicler.core.formatting import format_timestamp
from chronicler.core.models import TranscriptLine

PLAINTEXT_EXPORT_WIDTH = 140


def format_plaintext(lines: list[TranscriptLine], include_timestamps: bool = False) -> str:
    """One wrapped block per line of speech, speakers aligned, blank lines left out."""
    lines = [line for line in lines if line.text.strip()]
    if not lines:
        return ""

    speaker_width = max(len(line.speaker_name or "Unknown") for line in lines)

    formatted = []
    for line in lines:
        speaker_label = f"{(line.speaker_name or 'Unknown'):<{speaker_width}}: "
        prefix = (
            f"[{format_timestamp(line.start_time)}] {speaker_label}"
            if include_timestamps
            else speaker_label
        )
        continuation_indent = " " * len(prefix)
        sub_lines = [s for s in (part.strip() for part in line.text.split("\n")) if s]
        for i, sub_line in enumerate(sub_lines):
            formatted.append(
                textwrap.fill(
                    sub_line,
                    width=PLAINTEXT_EXPORT_WIDTH,
                    initial_indent=prefix if i == 0 else continuation_indent,
                    subsequent_indent=continuation_indent,
                )
            )
    return "\n".join(formatted)
