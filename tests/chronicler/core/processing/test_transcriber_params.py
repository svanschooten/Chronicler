from unittest.mock import MagicMock, patch

import pytest

from chronicler.core.config_sections import (
    AUTO_LANGUAGE,
    TranscriptionSettings,
    language_choices,
)
from chronicler.core.processing import transcriber
from chronicler.core.processing.transcriber import transcribe_audio


class _Segment:
    def __init__(self, text, start, end):
        self.text = text
        self.start = start
        self.end = end


@pytest.fixture(autouse=True)
def clear_model_cache():
    transcriber._model_cache.clear()
    yield
    transcriber._model_cache.clear()


@pytest.fixture
def whisper():
    model = MagicMock()
    model.transcribe.return_value = ([_Segment(" Hello ", 0.0, 1.0)], MagicMock())
    factory = MagicMock(return_value=model)
    with patch.dict("sys.modules", {"faster_whisper": MagicMock(WhisperModel=factory)}):
        yield factory, model


class TestTranscriptionParameters:
    def test_language_is_passed_through(self, whisper):
        _, model = whisper

        transcribe_audio("a.wav", "GM", language="nl")

        assert model.transcribe.call_args.kwargs["language"] == "nl"

    def test_auto_language_is_sent_as_none(self, whisper):
        _, model = whisper

        transcribe_audio("a.wav", "GM", language=AUTO_LANGUAGE)

        assert model.transcribe.call_args.kwargs["language"] is None

    def test_no_language_is_sent_as_none(self, whisper):
        _, model = whisper

        transcribe_audio("a.wav", "GM")

        assert model.transcribe.call_args.kwargs["language"] is None

    def test_no_speech_threshold_is_passed_through(self, whisper):
        _, model = whisper

        transcribe_audio("a.wav", "GM", no_speech_threshold=0.42)

        assert model.transcribe.call_args.kwargs["no_speech_threshold"] == 0.42

    def test_model_size_selects_the_model(self, whisper):
        factory, _ = whisper

        transcribe_audio("a.wav", "GM", model_size="small")

        assert factory.call_args.args[0] == "small"

    def test_device_and_compute_type_are_configurable(self, whisper):
        factory, _ = whisper

        transcribe_audio("a.wav", "GM", model_size="small", device="cuda", compute_type="float16")

        assert factory.call_args.kwargs["device"] == "cuda"
        assert factory.call_args.kwargs["compute_type"] == "float16"

    def test_models_are_cached_per_configuration(self, whisper):
        factory, _ = whisper

        transcribe_audio("a.wav", "GM", model_size="small")
        transcribe_audio("b.wav", "GM", model_size="small")

        assert factory.call_count == 1

    def test_a_different_device_is_a_different_cache_entry(self, whisper):
        factory, _ = whisper

        transcribe_audio("a.wav", "GM", model_size="small", device="cpu")
        transcribe_audio("b.wav", "GM", model_size="small", device="cuda")

        assert factory.call_count == 2

    def test_settings_supply_every_default(self, whisper):
        factory, model = whisper
        settings = TranscriptionSettings(
            model_size="medium", language="de", no_speech_threshold=0.31, device="cuda"
        )

        transcribe_audio("a.wav", "GM", settings=settings)

        assert factory.call_args.args[0] == "medium"
        assert factory.call_args.kwargs["device"] == "cuda"
        assert model.transcribe.call_args.kwargs["language"] == "de"
        assert model.transcribe.call_args.kwargs["no_speech_threshold"] == 0.31

    def test_explicit_arguments_win_over_settings(self, whisper):
        factory, model = whisper
        settings = TranscriptionSettings(model_size="medium", language="de")

        transcribe_audio("a.wav", "GM", language="fr", model_size="tiny", settings=settings)

        assert factory.call_args.args[0] == "tiny"
        assert model.transcribe.call_args.kwargs["language"] == "fr"

    def test_segments_still_become_attributed_lines(self, whisper):
        lines = transcribe_audio("a.wav", "GM")

        assert [(line.speaker_name, line.text) for line in lines] == [("GM", "Hello")]


class TestLanguageChoices:
    def test_auto_is_always_first(self):
        assert language_choices()[0] == AUTO_LANGUAGE

    def test_configured_languages_are_offered(self):
        settings = TranscriptionSettings(available_languages=["nl", "de"])

        assert language_choices(settings) == [AUTO_LANGUAGE, "de", "nl"]

    def test_ui_locales_are_always_available(self):
        settings = TranscriptionSettings(available_languages=["ja"])

        choices = language_choices(settings, ui_locales=["en", "nl"])

        assert set(choices) >= {AUTO_LANGUAGE, "ja", "en", "nl"}

    def test_the_configured_language_is_always_offered_even_if_unlisted(self):
        settings = TranscriptionSettings(available_languages=["nl"], language="pt")

        assert "pt" in language_choices(settings)

    def test_choices_are_deduplicated(self):
        settings = TranscriptionSettings(available_languages=["nl", "nl", "en"])

        choices = language_choices(settings, ui_locales=["en"])

        assert len(choices) == len(set(choices))

    def test_defaults_are_a_usable_set(self):
        choices = language_choices()

        assert "en" in choices
        assert "nl" in choices
        assert len(choices) > 5
