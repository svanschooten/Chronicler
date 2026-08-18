import re
from abc import ABC, abstractmethod

from chronicler.core.formatting import parse_timestamp
from chronicler.core.models import TranscriptLine
from chronicler.core.processing.regex_guard import assert_safe_pattern


class Importer(ABC):
    @abstractmethod
    def parse(self, content: str, start_offset: float = 0.0) -> list[TranscriptLine]:
        """`start_offset` is where this file begins on the chronicle's timeline -
        non-zero when appending to a transcript that already has lines. It's a
        parse-time input rather than something the caller shifts onto the returned
        lines, so every line is built with its final timing (see
        ImportHandler.handle_import).
        """


class RegexImporter(Importer):
    def __init__(
        self,
        line_regex: str,
        speaker_group: int = 1,
        text_group: int = 2,
        timestamp_group: int | None = None,
    ):
        # Defense in depth: TaskService.queue_import already rejects unsafe patterns
        # at submission time, but RegexImporter can be constructed directly by any
        # other caller, so the check belongs here too.
        assert_safe_pattern(line_regex)
        self.line_regex = re.compile(line_regex)
        self.speaker_group = speaker_group
        self.text_group = text_group
        self.timestamp_group = timestamp_group

    def parse(self, content: str, start_offset: float = 0.0) -> list[TranscriptLine]:
        # current_text's lines are joined with "\n", not " ": the source's own line
        # breaks within one speaker's turn are meaningful structure (see export -
        # TranscriptService.export_plaintext prints each as its own indented line
        # rather than flattening the turn into one wrapped paragraph). Cleaning
        # (TranscriptCleaner) already normalizes all whitespace including these when
        # it merges consecutive same-speaker turns, so this doesn't change cleaned
        # output.
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
                # Continuation line
                if current_speaker:
                    current_text.append(line.strip())
            else:
                # Maybe a line without speaker that is NOT indented?
                # For now let's assume it's just text if we have a speaker.
                if current_speaker:
                    current_text.append(line.strip())

        flush_current_turn()

        if self.timestamp_group is not None:
            # Only a start time is captured per cue - derive each line's end_time
            # from the *next* line's start_time (the last line is left zero-length,
            # its end equal to its own start, since there's nothing to derive it
            # from).
            for i, transcript_line in enumerate(transcript_lines):
                if i + 1 < len(transcript_lines):
                    transcript_line.end_time = transcript_lines[i + 1].start_time
        else:
            # Text sources have no real timestamps, but get_lines() orders by
            # start_time - leaving every line at 0.0 made that order an accident of
            # however SQLite happened to break the tie, not a guarantee. Sequential
            # indices make parse order the persisted order, and give
            # handle_import's "append" mode a meaningful offset to build on (see
            # WorkerHandlers.handle_import).
            for index, transcript_line in enumerate(transcript_lines):
                transcript_line.start_time = start_offset + index
                transcript_line.end_time = start_offset + index + 1

        return transcript_lines


class DefaultImporter(RegexImporter):
    def __init__(self):
        # Default regex for "Speaker  : text"
        super().__init__(r"^([A-Za-z0-9 _]+)\s*:(.*)$")
