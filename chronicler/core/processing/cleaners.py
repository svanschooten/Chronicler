from chronicler.core.models import TranscriptLine


class TranscriptCleaner:
    def clean(self, lines: list[TranscriptLine]) -> list[TranscriptLine]:
        if not lines:
            return []

        cleaned_lines = []
        current_line = None

        for line in lines:
            # Normalize text: strip and replace multiple spaces with single space
            text = " ".join(line.text.split())

            if (
                current_line
                and current_line.speaker_id == line.speaker_id
                and current_line.speaker_name == line.speaker_name
            ):
                # Merge with current line
                current_line.text += " " + text
                current_line.end_time = line.end_time
            else:
                # New line
                if current_line:
                    current_line.text = " ".join(current_line.text.split())
                    cleaned_lines.append(current_line)

                current_line = line.model_copy()
                current_line.text = text

        if current_line:
            current_line.text = " ".join(current_line.text.split())
            cleaned_lines.append(current_line)

        return cleaned_lines
