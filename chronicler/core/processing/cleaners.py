"""The transcript cleaning pipeline: an ordered, configurable set of single-purpose rules."""

import re
import unicodedata
from abc import ABC, abstractmethod

from chronicler.core.config_sections import CleaningSettings, HallucinationMatch
from chronicler.core.models import TranscriptLine


def normalize_for_comparison(text: str) -> str:
    """Casefolded text with surrounding punctuation and whitespace removed."""
    stripped = text.strip()
    while stripped and unicodedata.category(stripped[0]).startswith("P"):
        stripped = stripped[1:]
    while stripped and unicodedata.category(stripped[-1]).startswith("P"):
        stripped = stripped[:-1]
    return " ".join(stripped.split()).casefold()


class CleaningRule(ABC):
    """One transformation over a transcript, returning a new list of lines."""

    @abstractmethod
    def apply(self, lines: list[TranscriptLine]) -> list[TranscriptLine]: ...


class CollapseWhitespace(CleaningRule):
    """Normalises every run of whitespace, including newlines, to a single space."""

    def apply(self, lines: list[TranscriptLine]) -> list[TranscriptLine]:
        result = []
        for line in lines:
            copy = line.model_copy()
            copy.text = " ".join(line.text.split())
            result.append(copy)
        return result


class StripPatterns(CleaningRule):
    """Removes every match of the configured patterns from each line."""

    def __init__(self, patterns: list[str]):
        self._patterns = [re.compile(pattern) for pattern in patterns]

    def apply(self, lines: list[TranscriptLine]) -> list[TranscriptLine]:
        if not self._patterns:
            return list(lines)
        result = []
        for line in lines:
            text = line.text
            for pattern in self._patterns:
                text = pattern.sub("", text)
            copy = line.model_copy()
            copy.text = text
            result.append(copy)
        return result


class DropEmpty(CleaningRule):
    """Removes lines with no text left in them."""

    def apply(self, lines: list[TranscriptLine]) -> list[TranscriptLine]:
        return [line for line in lines if line.text.strip()]


class DropHallucinations(CleaningRule):
    """Removes lines matching a phrase the model is known to invent during silence."""

    def __init__(self, phrases: list[str], match: HallucinationMatch):
        self._match = match
        self._phrases = phrases
        self._exact = set(phrases)
        self._normalized = {normalize_for_comparison(phrase) for phrase in phrases}
        self._regexes = (
            [re.compile(phrase, re.IGNORECASE) for phrase in phrases] if match == "regex" else []
        )

    def apply(self, lines: list[TranscriptLine]) -> list[TranscriptLine]:
        if not self._phrases:
            return list(lines)
        return [line for line in lines if not self._is_hallucination(line.text)]

    def _is_hallucination(self, text: str) -> bool:
        if self._match == "exact":
            return text in self._exact
        if self._match == "regex":
            return any(pattern.fullmatch(text.strip()) for pattern in self._regexes)
        return normalize_for_comparison(text) in self._normalized


class DropShortLines(CleaningRule):
    """Removes lines shorter than the configured minimum, measured after stripping."""

    def __init__(self, min_characters: int):
        self._min_characters = min_characters

    def apply(self, lines: list[TranscriptLine]) -> list[TranscriptLine]:
        if self._min_characters <= 0:
            return list(lines)
        return [line for line in lines if len(line.text.strip()) >= self._min_characters]


class DropDuplicateSegments(CleaningRule):
    """Removes a line repeating another with the same speaker, text and rounded times."""

    def apply(self, lines: list[TranscriptLine]) -> list[TranscriptLine]:
        seen: set[tuple[str | None, str, int, int]] = set()
        result = []
        for line in lines:
            key = (
                line.speaker_name,
                normalize_for_comparison(line.text),
                round(line.start_time),
                round(line.end_time),
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(line)
        return result


class DropRepeats(CleaningRule):
    """Removes a line repeating that speaker's previous line within the time window."""

    def __init__(self, window_seconds: float):
        self._window = window_seconds

    def apply(self, lines: list[TranscriptLine]) -> list[TranscriptLine]:
        if self._window <= 0:
            return list(lines)
        last_kept: dict[tuple[str | None, str], float] = {}
        result = []
        for line in lines:
            key = (line.speaker_name, normalize_for_comparison(line.text))
            previous = last_kept.get(key)
            if previous is not None and line.start_time - previous <= self._window:
                continue
            last_kept[key] = line.start_time
            result.append(line)
        return result


class MergeSameSpeaker(CleaningRule):
    """Joins consecutive turns by one speaker into a single line spanning both times."""

    def apply(self, lines: list[TranscriptLine]) -> list[TranscriptLine]:
        merged: list[TranscriptLine] = []
        current: TranscriptLine | None = None
        for line in lines:
            same_speaker = (
                current is not None
                and current.speaker_id == line.speaker_id
                and current.speaker_name == line.speaker_name
            )
            if same_speaker and current is not None:
                current.text = f"{current.text} {line.text}".strip()
                current.end_time = line.end_time
                continue
            if current is not None:
                merged.append(current)
            current = line.model_copy()
        if current is not None:
            merged.append(current)
        return merged


def build_pipeline(settings: CleaningSettings) -> list[CleaningRule]:
    """The enabled rules, in the order they must run."""
    rules: list[CleaningRule] = []
    if settings.collapse_whitespace:
        rules.append(CollapseWhitespace())
    rules.append(StripPatterns(settings.strip_patterns))
    rules.append(DropEmpty())
    if settings.drop_hallucinations:
        rules.append(
            DropHallucinations(settings.hallucination_phrases, settings.hallucination_match)
        )
    rules.append(DropShortLines(settings.min_characters))
    if settings.drop_duplicate_segments:
        rules.append(DropDuplicateSegments())
    if settings.drop_repeats:
        rules.append(DropRepeats(settings.repetition_window_seconds))
    if settings.merge_same_speaker:
        rules.append(MergeSameSpeaker())
    return rules


class TranscriptCleaner:
    """Runs the configured cleaning rules over a transcript."""

    def __init__(self, settings: CleaningSettings | None = None):
        self.settings = settings or CleaningSettings()
        self._rules = build_pipeline(self.settings)

    def clean(self, lines: list[TranscriptLine]) -> list[TranscriptLine]:
        result = list(lines)
        for rule in self._rules:
            result = rule.apply(result)
        return result
