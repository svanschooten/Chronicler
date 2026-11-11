from pathlib import Path

import pytest

from chronicler.core.config import CONFIG_FILE_ENV_VAR, Settings
from chronicler.core.wizard import default_workspace_path, supported_languages


@pytest.fixture(autouse=True)
def _isolate_every_test(isolated_config):
    """Every test here builds a Settings(); see the shared fixture in tests/conftest.py."""


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

        target = tmp_path / "settings.yaml"
        monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(target))

        Settings().save()
        stored = yaml.safe_load(target.read_text())

        for section in ("transcription", "cleaning", "normalization", "llm", "summary", "ui"):
            assert section in stored, f"{section} missing from a clean install"
