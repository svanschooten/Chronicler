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
        turns = self._collect_turns(content, start_offset)
        self._assign_times(turns, start_offset)
        return turns

    def _collect_turns(self, content: str, start_offset: float) -> list[TranscriptLine]:
        """
        One TranscriptLine per speaker turn.

        A line that does not match the pattern continues the turn above it, indented or
        not - wrapped transcripts and hand-edited ones both produce those.
        """
        turns: list[TranscriptLine] = []
        speaker: str | None = None
        text: list[str] = []
        start_time = start_offset

        def flush() -> None:
            if speaker:
                turns.append(
                    TranscriptLine(
                        speaker_name=speaker,
                        text="\n".join(text).strip(),
                        start_time=start_time,
                        end_time=start_time,
                    )
                )

        for line in content.splitlines():
            if not line.strip():
                continue

            match = self.line_regex.match(line)
            if match is None:
                if speaker:
                    text.append(line.strip())
                continue

            flush()
            speaker = match.group(self.speaker_group).strip()
            text = [match.group(self.text_group).strip()]
            if self.timestamp_group is not None:
                start_time = start_offset + parse_timestamp(
                    match.group(self.timestamp_group).strip()
                )

        flush()
        return turns

    def _assign_times(self, turns: list[TranscriptLine], start_offset: float) -> None:
        """
        A turn runs until the next one starts. Without a timestamp group there are no real
        times at all, so each turn gets one synthetic second - see docs/transcription.md
        for why SRT export refuses those.
        """
        if self.timestamp_group is not None:
            for turn, following in zip(turns, turns[1:], strict=False):
                turn.end_time = following.start_time
            return

        for index, turn in enumerate(turns):
            turn.start_time = start_offset + index
            turn.end_time = start_offset + index + 1


class DefaultImporter(RegexImporter):
    def __init__(self):
        super().__init__(r"^([A-Za-z0-9 _]+)\s*:(.*)$")
