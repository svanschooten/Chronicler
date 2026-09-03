"""Grouped settings sections nested under `Settings`."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from chronicler.core.processing.regex_guard import UnsafePatternError, assert_safe_pattern

DEFAULT_HALLUCINATION_PHRASES: list[str] = [
    "you",
    "Thanks for watching!",
    "Thanks for watching.",
    "Thank you for watching.",
    "Please subscribe.",
    "Subtitles by the Amara.org community",
    ".",
    "...",
]

AUTO_LANGUAGE = "auto"

DEFAULT_AVAILABLE_LANGUAGES: list[str] = [
    "en",
    "nl",
    "de",
    "fr",
    "es",
    "it",
    "pt",
    "pl",
    "sv",
    "da",
    "no",
    "fi",
    "ja",
    "zh",
]

WHISPER_MODEL_SIZES: list[str] = [
    "tiny",
    "base",
    "small",
    "medium",
    "large-v3",
    "turbo",
]

HallucinationMatch = Literal["exact", "normalized", "regex"]
LlmProvider = Literal["none", "openai_compatible", "llama_cpp"]


def _non_blank(values: list[str]) -> list[str]:
    return [value.strip() for value in values if value.strip()]


def _guard_patterns(patterns: list[str]) -> list[str]:
    for pattern in patterns:
        try:
            assert_safe_pattern(pattern)
        except UnsafePatternError as error:
            raise ValueError(str(error)) from error
    return patterns


class TranscriptionSettings(BaseModel):
    """Defaults for TRANSCRIBE tasks, overridable per task."""

    model_config = ConfigDict(protected_namespaces=())

    model_size: str = "base"
    language: str | None = None
    no_speech_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    normalize_first: bool = False
    device: str = "cpu"
    compute_type: str = "int8"
    available_languages: list[str] = Field(
        default_factory=lambda: list(DEFAULT_AVAILABLE_LANGUAGES)
    )

    @field_validator("language", mode="before")
    @classmethod
    def _normalize_language(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        cleaned = value.strip().lower()
        if not cleaned or cleaned == AUTO_LANGUAGE:
            return None
        return cleaned

    @field_validator("available_languages")
    @classmethod
    def _clean_languages(cls, value: list[str]) -> list[str]:
        return [item.strip().lower() for item in value if item.strip()]


class CleaningSettings(BaseModel):
    """Which cleaning rules run, and how each is parameterised."""

    collapse_whitespace: bool = True
    merge_same_speaker: bool = True
    drop_hallucinations: bool = True
    hallucination_phrases: list[str] = Field(
        default_factory=lambda: list(DEFAULT_HALLUCINATION_PHRASES)
    )
    hallucination_match: HallucinationMatch = "normalized"
    drop_repeats: bool = True
    repetition_window_seconds: float = Field(default=200.0, ge=0.0)
    drop_duplicate_segments: bool = True
    min_characters: int = Field(default=0, ge=0)
    strip_patterns: list[str] = Field(default_factory=list)

    @field_validator("hallucination_phrases", "strip_patterns")
    @classmethod
    def _drop_blanks(cls, value: list[str]) -> list[str]:
        return _non_blank(value)

    @field_validator("strip_patterns")
    @classmethod
    def _guard_strip_patterns(cls, value: list[str]) -> list[str]:
        return _guard_patterns(value)

    def model_post_init(self, _context: Any) -> None:
        if self.hallucination_match == "regex":
            _guard_patterns(self.hallucination_phrases)


class NormalizationSettings(BaseModel):
    """Loudness targets for the NORMALIZE task, in EBU R128 units."""

    target_lufs: float = Field(default=-18.0, ge=-70.0, le=0.0)
    true_peak: float = Field(default=-1.5, ge=-9.0, le=0.0)
    loudness_range: float = Field(default=7.0, gt=0.0, le=20.0)
    denoise: bool = False
    highpass_hz: int | None = Field(default=None, ge=0, le=1000)


class LlmSettings(BaseModel):
    """Which language model backs summarisation, and how to reach it."""

    model_config = ConfigDict(protected_namespaces=())

    provider: LlmProvider = "none"
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    model_path: str | None = None
    context_window: int = Field(default=8192, gt=0)
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, gt=0)

    @field_validator("base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str | None) -> str | None:
        return value.rstrip("/") if value else value

    @property
    def is_configured(self) -> bool:
        if self.provider == "openai_compatible":
            return bool(self.base_url) and bool(self.model)
        if self.provider == "llama_cpp":
            return bool(self.model_path)
        return False


DEFAULT_SYSTEM_PROMPT = (
    "You are summarising a transcript of a real recorded conversation. Be accurate and "
    "concise, never invent details, and keep the participants' own names."
)

DEFAULT_CHUNK_PROMPT = (
    "Below is one section of a longer transcript. Extract the important events, decisions "
    "and points of discussion as short single-line bullet points. Leave out small talk and "
    "anything not carried forward. Do not add a preamble."
)

DEFAULT_RECAP_PROMPT = (
    "Below are notes taken from a transcript. Write a flowing recap of what happened. "
    'Do not begin with "The session began with". Do not add a preamble or a title.'
)


class SummarySettings(BaseModel):
    """Prompts and limits for the SUMMARIZE task, overridable per task."""

    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    chunk_prompt: str = DEFAULT_CHUNK_PROMPT
    recap_prompt: str = DEFAULT_RECAP_PROMPT
    max_tokens: int = Field(default=1024, gt=0)
    language: str | None = None

    @field_validator("system_prompt", "chunk_prompt", "recap_prompt")
    @classmethod
    def _require_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("A prompt cannot be empty")
        return cleaned

    @field_validator("language", mode="before")
    @classmethod
    def _normalize_language(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        cleaned = value.strip().lower()
        if not cleaned or cleaned == AUTO_LANGUAGE:
            return None
        return cleaned


class ExtrasSettings(BaseModel):
    """How Chronicler handles an optional dependency it needs but does not have."""

    auto_install: bool = False


class UiSettings(BaseModel):
    """Presentation preferences that are not tied to a workspace."""

    locale: str = "en"

    @field_validator("locale")
    @classmethod
    def _normalize_locale(cls, value: str) -> str:
        return value.strip().lower() or "en"


def language_choices(
    settings: "TranscriptionSettings | None" = None,
    ui_locales: list[str] | None = None,
) -> list[str]:
    """Every language a transcribe task may be given, with `auto` first."""
    settings = settings or TranscriptionSettings()
    offered = set(settings.available_languages) | set(ui_locales or [])
    if settings.language:
        offered.add(settings.language)
    return [AUTO_LANGUAGE, *sorted(offered)]
