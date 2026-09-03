import pytest
from pydantic import ValidationError

from chronicler.core.config_sections import (
    DEFAULT_HALLUCINATION_PHRASES,
    CleaningSettings,
    ExtrasSettings,
    LlmSettings,
    NormalizationSettings,
    TranscriptionSettings,
    UiSettings,
)


class TestCleaningSettings:
    def test_defaults_are_usable_without_any_configuration(self):
        settings = CleaningSettings()

        assert settings.collapse_whitespace is True
        assert settings.merge_same_speaker is True
        assert settings.drop_hallucinations is True
        assert settings.drop_repeats is True
        assert settings.hallucination_phrases == DEFAULT_HALLUCINATION_PHRASES

    def test_default_phrases_cover_the_classic_whisper_silence_artifacts(self):
        normalized = {phrase.casefold() for phrase in DEFAULT_HALLUCINATION_PHRASES}

        assert "you" in normalized
        assert "thanks for watching!" in normalized
        assert "please subscribe." in normalized

    def test_defaults_favour_precision_over_recall(self):
        """Phrases that are also ordinary speech stay out of the defaults.

        Whisper does hallucinate these, but deleting a real "Okay." silently loses
        dialogue, which is worse than leaving an invented one in.
        """
        normalized = {phrase.casefold() for phrase in DEFAULT_HALLUCINATION_PHRASES}

        assert "okay." not in normalized
        assert "thank you." not in normalized
        assert "bye." not in normalized

    def test_mutating_one_instances_phrases_does_not_affect_the_next(self):
        first = CleaningSettings()
        first.hallucination_phrases.append("mutated")

        assert "mutated" not in CleaningSettings().hallucination_phrases

    def test_phrases_are_replaced_wholesale_not_appended(self):
        settings = CleaningSettings(hallucination_phrases=["Ondertiteling door"])

        assert settings.hallucination_phrases == ["Ondertiteling door"]

    def test_blank_phrases_are_dropped(self):
        settings = CleaningSettings(hallucination_phrases=["you", "   ", ""])

        assert settings.hallucination_phrases == ["you"]

    def test_repetition_window_must_not_be_negative(self):
        with pytest.raises(ValidationError):
            CleaningSettings(repetition_window_seconds=-1.0)

    def test_min_characters_must_not_be_negative(self):
        with pytest.raises(ValidationError):
            CleaningSettings(min_characters=-1)

    def test_unsafe_strip_pattern_is_rejected(self):
        with pytest.raises(ValidationError) as excinfo:
            CleaningSettings(strip_patterns=[r"(a+)+$"])

        assert "backtracking" in str(excinfo.value).lower()

    def test_invalid_strip_pattern_is_rejected(self):
        with pytest.raises(ValidationError):
            CleaningSettings(strip_patterns=["[unclosed"])

    def test_safe_strip_pattern_is_accepted(self):
        settings = CleaningSettings(strip_patterns=[r"^\[.*\]$"])

        assert settings.strip_patterns == [r"^\[.*\]$"]

    def test_regex_hallucination_phrases_are_guarded_too(self):
        with pytest.raises(ValidationError):
            CleaningSettings(hallucination_match="regex", hallucination_phrases=[r"(a|a)*b"])

    def test_regex_hallucination_phrases_are_allowed_when_safe(self):
        settings = CleaningSettings(hallucination_match="regex", hallucination_phrases=[r"^\W*$"])

        assert settings.hallucination_phrases == [r"^\W*$"]

    def test_hallucination_match_mode_is_constrained(self):
        with pytest.raises(ValidationError):
            CleaningSettings(hallucination_match="fuzzy")


class TestTranscriptionSettings:
    def test_defaults(self):
        settings = TranscriptionSettings()

        assert settings.model_size == "base"
        assert settings.language is None
        assert settings.no_speech_threshold == 0.6
        assert settings.normalize_first is False

    def test_no_speech_threshold_is_a_probability(self):
        with pytest.raises(ValidationError):
            TranscriptionSettings(no_speech_threshold=1.5)
        with pytest.raises(ValidationError):
            TranscriptionSettings(no_speech_threshold=-0.1)

    def test_language_is_normalized_to_lowercase(self):
        assert TranscriptionSettings(language="EN").language == "en"

    def test_blank_language_means_autodetect(self):
        assert TranscriptionSettings(language="  ").language is None


class TestNormalizationSettings:
    def test_defaults_target_speech_loudness(self):
        settings = NormalizationSettings()

        assert settings.target_lufs == -18.0
        assert settings.true_peak == -1.5
        assert settings.denoise is False
        assert settings.highpass_hz is None

    def test_target_lufs_must_be_negative(self):
        with pytest.raises(ValidationError):
            NormalizationSettings(target_lufs=3.0)

    def test_true_peak_ceiling_is_bounded(self):
        with pytest.raises(ValidationError):
            NormalizationSettings(true_peak=1.0)

    def test_loudness_range_must_be_positive(self):
        with pytest.raises(ValidationError):
            NormalizationSettings(loudness_range=0.0)


class TestLlmSettings:
    def test_disabled_by_default(self):
        settings = LlmSettings()

        assert settings.provider == "none"
        assert settings.is_configured is False

    def test_openai_compatible_needs_a_base_url(self):
        settings = LlmSettings(provider="openai_compatible", model="qwen3")

        assert settings.is_configured is False

    def test_openai_compatible_needs_a_model(self):
        settings = LlmSettings(provider="openai_compatible", base_url="http://localhost:8080/v1")

        assert settings.is_configured is False

    def test_openai_compatible_is_configured_with_url_and_model(self):
        settings = LlmSettings(
            provider="openai_compatible",
            base_url="http://localhost:8080/v1",
            model="qwen3",
        )

        assert settings.is_configured is True

    def test_llama_cpp_needs_a_model_path(self):
        assert LlmSettings(provider="llama_cpp").is_configured is False
        assert LlmSettings(provider="llama_cpp", model_path="/models/q4.gguf").is_configured is True

    def test_trailing_slash_is_stripped_from_base_url(self):
        settings = LlmSettings(base_url="http://localhost:8080/v1/")

        assert settings.base_url == "http://localhost:8080/v1"

    def test_unknown_provider_is_rejected(self):
        with pytest.raises(ValidationError):
            LlmSettings(provider="magic")

    def test_temperature_is_bounded(self):
        with pytest.raises(ValidationError):
            LlmSettings(temperature=3.0)


class TestUiSettings:
    def test_default_locale_is_english(self):
        assert UiSettings().locale == "en"

    def test_locale_is_normalized(self):
        assert UiSettings(locale="NL").locale == "nl"


class TestExtrasSettings:
    def test_downloads_are_confirmed_by_default(self):
        assert ExtrasSettings().auto_install is False

    def test_confirmation_can_be_waived(self):
        assert ExtrasSettings(auto_install=True).auto_install is True
