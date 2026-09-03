import pytest
import yaml

from chronicler.core.config import CONFIG_FILE_ENV_VAR, Settings, get_settings
from chronicler.desktop.views.settings.editor import SettingsEditor


@pytest.fixture
def config_file(tmp_path, monkeypatch):
    path = tmp_path / "chronicler.yaml"
    path.write_text(yaml.dump({"app_name": "Chronicler", "dark_mode": True}))
    monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(path))
    get_settings.cache_clear()
    yield path
    get_settings.cache_clear()


@pytest.fixture
def editor(config_file):
    return SettingsEditor(Settings()), config_file


class TestPersistence:
    def test_a_change_is_written_to_the_tracked_config_file(self, editor):
        settings_editor, path = editor

        settings_editor.set("transcription.language", "nl")
        settings_editor.save()

        assert yaml.safe_load(path.read_text())["transcription"]["language"] == "nl"

    def test_the_saved_file_reloads_into_equivalent_settings(self, editor):
        settings_editor, _ = editor
        settings_editor.set("transcription.no_speech_threshold", 0.42)
        settings_editor.set("ui.locale", "nl")
        settings_editor.save()

        get_settings.cache_clear()
        reloaded = Settings()

        assert reloaded.transcription.no_speech_threshold == 0.42
        assert reloaded.ui.locale == "nl"

    def test_unrelated_existing_values_survive(self, editor):
        settings_editor, path = editor

        settings_editor.set("transcription.language", "de")
        settings_editor.save()

        assert yaml.safe_load(path.read_text())["dark_mode"] is True

    def test_saving_reports_the_file_written(self, editor):
        settings_editor, path = editor

        assert settings_editor.save() == path


class TestSetting:
    def test_sets_a_nested_value(self, editor):
        settings_editor, _ = editor

        settings_editor.set("transcription.model_size", "small")

        assert settings_editor.settings.transcription.model_size == "small"

    def test_sets_a_top_level_value(self, editor):
        settings_editor, _ = editor

        settings_editor.set("dark_mode", False)

        assert settings_editor.settings.dark_mode is False

    def test_auto_language_becomes_none(self, editor):
        settings_editor, _ = editor

        settings_editor.set("transcription.language", "auto")

        assert settings_editor.settings.transcription.language is None

    def test_a_blank_string_becomes_none_for_optional_fields(self, editor):
        settings_editor, _ = editor
        settings_editor.set("llm.base_url", "http://x/v1")

        settings_editor.set("llm.base_url", "")

        assert settings_editor.settings.llm.base_url is None

    def test_numeric_strings_are_coerced(self, editor):
        settings_editor, _ = editor

        settings_editor.set("transcription.no_speech_threshold", "0.25")

        assert settings_editor.settings.transcription.no_speech_threshold == 0.25

    def test_an_invalid_value_raises_and_leaves_the_setting_untouched(self, editor):
        settings_editor, _ = editor
        before = settings_editor.settings.transcription.no_speech_threshold

        with pytest.raises(ValueError):
            settings_editor.set("transcription.no_speech_threshold", 5.0)

        assert settings_editor.settings.transcription.no_speech_threshold == before

    def test_an_unparseable_number_raises(self, editor):
        settings_editor, _ = editor

        with pytest.raises(ValueError):
            settings_editor.set("transcription.no_speech_threshold", "not a number")

    def test_an_unknown_path_raises(self, editor):
        settings_editor, _ = editor

        with pytest.raises(KeyError):
            settings_editor.set("transcription.nonsense", 1)

    def test_an_unknown_section_raises(self, editor):
        settings_editor, _ = editor

        with pytest.raises(KeyError):
            settings_editor.set("nonsense.field", 1)


class TestListSettings:
    def test_a_newline_separated_list_is_split(self, editor):
        settings_editor, _ = editor

        settings_editor.set("cleaning.hallucination_phrases", "you\nOndertiteling door\n")

        assert settings_editor.settings.cleaning.hallucination_phrases == [
            "you",
            "Ondertiteling door",
        ]

    def test_a_real_list_is_accepted_as_is(self, editor):
        settings_editor, _ = editor

        settings_editor.set("cleaning.hallucination_phrases", ["a", "b"])

        assert settings_editor.settings.cleaning.hallucination_phrases == ["a", "b"]

    def test_an_unsafe_pattern_is_rejected(self, editor):
        settings_editor, _ = editor

        with pytest.raises(ValueError):
            settings_editor.set("cleaning.strip_patterns", "(a+)+$")

    def test_lists_round_trip_through_the_config_file(self, editor):
        settings_editor, _ = editor
        settings_editor.set("cleaning.hallucination_phrases", "eerste\ntweede")
        settings_editor.save()

        get_settings.cache_clear()

        assert Settings().cleaning.hallucination_phrases == ["eerste", "tweede"]

    def test_as_text_renders_a_list_for_editing(self, editor):
        settings_editor, _ = editor
        settings_editor.set("cleaning.hallucination_phrases", ["a", "b"])

        assert settings_editor.as_text("cleaning.hallucination_phrases") == "a\nb"


class TestReading:
    def test_get_returns_the_current_value(self, editor):
        settings_editor, _ = editor

        assert settings_editor.get("transcription.model_size") == "base"

    def test_language_reads_back_as_auto_when_unset(self, editor):
        settings_editor, _ = editor

        assert settings_editor.get_language() == "auto"

    def test_language_reads_back_as_itself_when_set(self, editor):
        settings_editor, _ = editor
        settings_editor.set("transcription.language", "nl")

        assert settings_editor.get_language() == "nl"

    def test_restoring_defaults_for_one_section(self, editor):
        settings_editor, _ = editor
        settings_editor.set("cleaning.hallucination_phrases", ["custom"])

        settings_editor.restore_defaults("cleaning")

        assert settings_editor.settings.cleaning.hallucination_phrases != ["custom"]
        assert settings_editor.settings.cleaning.drop_repeats is True

    def test_restoring_an_unknown_section_raises(self, editor):
        settings_editor, _ = editor

        with pytest.raises(KeyError):
            settings_editor.restore_defaults("nonsense")


@pytest.fixture
def subject(editor):
    """Just the editor, for the tests that do not touch the file."""
    return editor[0]


class TestWouldChange:
    def test_the_same_text_is_not_a_change(self, subject):
        assert subject.would_change("transcription.model_size", "base") is False

    def test_a_different_value_is_a_change(self, subject):
        assert subject.would_change("transcription.model_size", "small") is True

    def test_a_float_typed_back_in_its_rendered_form_is_not_a_change(self, subject):
        assert subject.would_change("transcription.no_speech_threshold", "0.6") is False

    def test_a_float_with_trailing_zeroes_is_not_a_change(self, subject):
        assert subject.would_change("transcription.no_speech_threshold", "0.60") is False

    def test_a_real_float_edit_is_a_change(self, subject):
        assert subject.would_change("transcription.no_speech_threshold", "0.35") is True

    def test_a_list_differing_only_in_blank_lines_is_not_a_change(self, subject):
        current = subject.as_text("cleaning.hallucination_phrases")

        assert subject.would_change("cleaning.hallucination_phrases", f"{current}\n\n") is False

    def test_a_list_gaining_an_entry_is_a_change(self, subject):
        current = subject.as_text("cleaning.hallucination_phrases")

        assert subject.would_change("cleaning.hallucination_phrases", f"{current}\nuhm") is True

    def test_auto_and_a_blank_language_are_the_same_thing(self, subject):
        assert subject.would_change("transcription.language", "auto") is False
        assert subject.would_change("transcription.language", "") is False

    def test_a_boolean_toggle_is_a_change(self, subject):
        assert subject.would_change("transcription.normalize_first", True) is True
        assert subject.would_change("transcription.normalize_first", False) is False

    def test_a_value_that_cannot_be_coerced_counts_as_a_change_so_it_is_reported(self, subject):
        """An invalid entry must reach `set()` to produce its error, not be swallowed."""
        assert subject.would_change("transcription.no_speech_threshold", "banana") is True
