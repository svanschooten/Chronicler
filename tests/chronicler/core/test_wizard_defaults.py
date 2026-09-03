from pathlib import Path
from unittest.mock import patch

from chronicler.core.config import Settings
from chronicler.core.wizard import (
    LanguageStep,
    WorkspaceStep,
    default_workspace_path,
    supported_languages,
)


class TestDefaultWorkspacePath:
    def test_it_sits_under_the_users_documents_when_present(self, tmp_path, monkeypatch):
        documents = tmp_path / "Documents"
        documents.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))

        assert default_workspace_path() == documents / "Chronicler"

    def test_it_falls_back_to_the_home_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))

        assert default_workspace_path() == tmp_path / "Chronicler"

    def test_it_is_always_absolute(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))

        assert default_workspace_path().is_absolute()


class TestSupportedLanguages:
    def test_the_three_shipped_languages_are_offered(self):
        assert supported_languages() == ["en", "nl", "de"]


class TestLanguageStep:
    def test_it_sets_both_the_interface_and_transcription_language(self):
        settings = Settings()

        with patch("builtins.input", return_value="2"):
            LanguageStep().run(settings)

        assert settings.ui.locale == "nl"
        assert settings.transcription.language == "nl"

    def test_the_default_is_english(self):
        settings = Settings()

        with patch("builtins.input", return_value=""):
            LanguageStep().run(settings)

        assert settings.ui.locale == "en"

    def test_german_can_be_chosen(self):
        settings = Settings()

        with patch("builtins.input", return_value="3"):
            LanguageStep().run(settings)

        assert settings.ui.locale == "de"
        assert settings.transcription.language == "de"

    def test_an_invalid_choice_reprompts(self):
        settings = Settings()

        with patch("builtins.input", side_effect=["9", "1"]):
            LanguageStep().run(settings)

        assert settings.ui.locale == "en"

    def test_it_is_satisfied_once_a_language_is_recorded(self):
        """
        transcription.language is the marker, not ui.locale: the locale has a working
        default of "en", so it can never say whether the step was actually run.
        """
        settings = Settings()
        assert LanguageStep().is_satisfied(settings) is False

        settings.transcription.language = "nl"
        assert LanguageStep().is_satisfied(settings) is True


class TestWorkspaceStep:
    def test_it_offers_the_os_aware_default(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))
        settings = Settings()

        with patch("builtins.input", return_value=""):
            WorkspaceStep().run(settings)

        assert settings.workspace_path == default_workspace_path()

    def test_a_typed_path_wins(self, tmp_path):
        settings = Settings()

        with patch("builtins.input", return_value=str(tmp_path / "elsewhere")):
            WorkspaceStep().run(settings)

        assert settings.workspace_path == tmp_path / "elsewhere"

    def test_a_relative_path_is_made_absolute(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        settings = Settings()

        with patch("builtins.input", return_value="relative-workspace"):
            WorkspaceStep().run(settings)

        assert settings.workspace_path.is_absolute()

    def test_a_home_shorthand_is_expanded(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        settings = Settings()

        with patch("builtins.input", return_value="~/MyChronicles"):
            WorkspaceStep().run(settings)

        assert settings.workspace_path == tmp_path / "MyChronicles"


class TestCleanInstallDefaults:
    def test_a_fresh_settings_object_has_every_section_populated(self):
        settings = Settings()

        assert settings.transcription.model_size
        assert settings.cleaning.hallucination_phrases
        assert settings.normalization.target_lufs
        assert settings.summary.recap_prompt
        assert settings.ui.locale

    def test_saving_a_fresh_install_writes_every_section(self, tmp_path, monkeypatch):
        import yaml

        from chronicler.core.config import CONFIG_FILE_ENV_VAR

        target = tmp_path / "settings.yaml"
        monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(target))

        Settings().save()
        stored = yaml.safe_load(target.read_text())

        for section in ("transcription", "cleaning", "normalization", "llm", "summary", "ui"):
            assert section in stored, f"{section} missing from a clean install"
