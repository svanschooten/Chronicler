import re
from abc import ABC, abstractmethod

from chronicler.core.formatting import parse_timestamp
from chronicler.core.models import TranscriptLine
from chronicler.core.processing.regex_guard import assert_safe_pattern


class Importer(ABC):
    @abstractmethod
    def parse(self, content: str, start_offset: float = 0.0) -> list[TranscriptLine]:
        """
        `start_offset` is where this file begins on the chronicle's timeline - non-zero
        when appending to a transcript that already has lines.
        """


class RegexImporter(Importer):
    def __init__(
        self,
        line_regex: str,
        speaker_group: int = 1,
        text_group: int = 2,
        timestamp_group: int | None = None,
    ):
        assert_safe_pattern(line_regex)
        self.line_regex = re.compile(line_regex)
        self.speaker_group = speaker_group
        self.text_group = text_group
        self.timestamp_group = timestamp_group

    def parse(self, content: str, start_offset: float = 0.0) -> list[TranscriptLine]:
        lines = content.splitlines()
        transcript_lines: list[TranscriptLine] = []
        current_speaker: str | None = None
        current_text: list[str] = []
        current_start_time = start_offset

        def flush_current_turn() -> None:
            if current_speaker:
                transcript_lines.append(
                    TranscriptLine(
                        speaker_name=current_speaker,
                        text="\n".join(current_text).strip(),
                        start_time=current_start_time,
                        end_time=current_start_time,
                    )
                )

        for line in lines:
            if not line.strip():
                continue

            match = self.line_regex.match(line)
            if match:
                flush_current_turn()
                current_speaker = match.group(self.speaker_group).strip()
                current_text = [match.group(self.text_group).strip()]
                if self.timestamp_group is not None:
                    current_start_time = start_offset + parse_timestamp(
                        match.group(self.timestamp_group).strip()
                    )
            elif line.startswith(" ") or line.startswith("\t"):
                if current_speaker:
                    current_text.append(line.strip())
            else:
                if current_speaker:
                    current_text.append(line.strip())

        flush_current_turn()

        if self.timestamp_group is not None:
            for i, transcript_line in enumerate(transcript_lines):
                if i + 1 < len(transcript_lines):
                    transcript_line.end_time = transcript_lines[i + 1].start_time
        else:
            for index, transcript_line in enumerate(transcript_lines):
                transcript_line.start_time = start_offset + index
                transcript_line.end_time = start_offset + index + 1

        return transcript_lines


class DefaultImporter(RegexImporter):
    def __init__(self):
        super().__init__(r"^([A-Za-z0-9 _]+)\s*:(.*)$")
