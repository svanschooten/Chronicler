import re
from abc import ABC, abstractmethod

from chronicler.core.models import TranscriptLine


class Importer(ABC):
    @abstractmethod
    def parse(self, content: str) -> list[TranscriptLine]:
        pass


class RegexImporter(Importer):
    def __init__(self, line_regex: str, speaker_group: int = 1, text_group: int = 2):
        self.line_regex = re.compile(line_regex)
        self.speaker_group = speaker_group
        self.text_group = text_group

    def parse(self, content: str) -> list[TranscriptLine]:
        lines = content.splitlines()
        transcript_lines = []
        current_speaker = None
        current_text = []

        for line in lines:
            if not line.strip():
                continue

            match = self.line_regex.match(line)
            if match:
                # New speaker line
                if current_speaker:
                    transcript_lines.append(
                        TranscriptLine(
                            speaker_name=current_speaker,
                            text=" ".join(current_text).strip(),
                            start_time=0.0,
                            end_time=0.0,
                        )
                    )
                current_speaker = match.group(self.speaker_group).strip()
                current_text = [match.group(self.text_group).strip()]
            elif line.startswith(" ") or line.startswith("\t"):
                # Continuation line
                if current_speaker:
                    current_text.append(line.strip())
            else:
                # Maybe a line without speaker that is NOT indented?
                # For now let's assume it's just text if we have a speaker.
                if current_speaker:
                    current_text.append(line.strip())

        # Add the last one
        if current_speaker:
            transcript_lines.append(
                TranscriptLine(
                    speaker_name=current_speaker,
                    text=" ".join(current_text).strip(),
                    start_time=0.0,
                    end_time=0.0,
                )
            )

        return transcript_lines


class DefaultImporter(RegexImporter):
    def __init__(self):
        # Default regex for "Speaker  : text"
        super().__init__(r"^([A-Za-z0-9 _]+)\s*:(.*)$")
