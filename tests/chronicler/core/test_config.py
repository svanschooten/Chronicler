import pytest
import yaml

from chronicler.core.config import (
    CONFIG_FILE_ENV_VAR,
    Settings,
    get_settings,
    is_config_initialized,
    resolve_config_file,
    set_config_file_override,
)


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch, tmp_path):
    """Keeps config resolution away from the developer's real configuration."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv(CONFIG_FILE_ENV_VAR, raising=False)
    get_settings.cache_clear()
    yield home
    get_settings.cache_clear()


def test_default_settings(monkeypatch, tmp_path):
    monkeypatch.setattr("chronicler.core.config.user_config_dir", lambda x: str(tmp_path))
    settings = Settings()
    assert settings.app_name == "Chronicler"
    assert settings.workspace_path is None


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("CHRONICLER_APP_NAME", "TestChronicler")
    settings = Settings()
    assert settings.app_name == "TestChronicler"


def test_get_settings_singleton():
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


def test_config_dir():
    settings = Settings()
    assert "Chronicler" in str(settings.config_dir)


def test_workspace_validation(tmp_path):
    non_existent = tmp_path / "missing"
    settings = Settings(workspace_path=non_existent)
    assert not settings.is_workspace_valid()

    existing = tmp_path / "exists"
    existing.mkdir()
    settings = Settings(workspace_path=existing)
    assert settings.is_workspace_valid()

    try:
        read_only = tmp_path / "readonly"
        read_only.mkdir(mode=0o555)
        settings = Settings(workspace_path=read_only)
        assert not settings.is_workspace_valid()
    finally:
        read_only.chmod(0o777)


def test_save_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(Settings, "config_dir", tmp_path)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    settings = Settings(workspace_path=workspace)
    settings.save()

    config_file = tmp_path / "settings.yaml"
    assert config_file.exists()

    with open(config_file) as f:
        data = yaml.safe_load(f)
        assert data["workspace_path"] == str(workspace)


def test_an_explicit_config_file_is_read_instead_of_the_defaults(monkeypatch, tmp_path):
    default = tmp_path / "home" / ".chronicler_config.yaml"
    default.write_text("app_name: FromDefaultLocation\n")
    explicit = tmp_path / "elsewhere" / "custom.yaml"
    explicit.parent.mkdir()
    explicit.write_text("app_name: FromExplicitFile\n")

    monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(explicit))

    assert resolve_config_file() == explicit
    assert Settings().app_name == "FromExplicitFile"


def test_a_missing_explicit_config_file_does_not_fall_back_to_the_defaults(
    monkeypatch, tmp_path, caplog
):
    """The whole point of --config is isolating an instance."""
    default = tmp_path / "home" / ".chronicler_config.yaml"
    default.write_text("app_name: FromDefaultLocation\n")

    monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(tmp_path / "does-not-exist.yaml"))

    with caplog.at_level("WARNING", logger="chronicler.core.config"):
        settings = Settings()

    assert resolve_config_file() is None
    assert settings.app_name == "Chronicler"
    assert any("does not exist" in record.message for record in caplog.records)


def test_an_explicit_config_file_is_expanded(monkeypatch, tmp_path):
    explicit = tmp_path / "home" / "custom.yaml"
    explicit.write_text("app_name: Expanded\n")

    monkeypatch.setenv(CONFIG_FILE_ENV_VAR, "~/custom.yaml")

    assert resolve_config_file() == explicit


def test_save_writes_to_the_explicit_config_file(monkeypatch, tmp_path):
    """
    A --config run that changes a setting must persist it where the caller asked, not into
    the default location.
    """
    explicit = tmp_path / "elsewhere" / "custom.yaml"
    monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(explicit))
    settings = Settings(app_name="Chronicler", dark_mode=False)

    written = settings.save()

    assert written == explicit
    assert yaml.safe_load(explicit.read_text())["dark_mode"] is False
    assert not (tmp_path / "home" / ".chronicler_config.yaml").exists()


def test_save_updates_the_home_config_when_that_is_what_is_in_use(tmp_path):
    home_config = tmp_path / "home" / ".chronicler_config.yaml"
    home_config.write_text("app_name: Chronicler\n")

    assert Settings().save_path() == home_config


def test_is_config_initialized_follows_the_explicit_override(monkeypatch, tmp_path):
    (tmp_path / "home" / ".chronicler_config.yaml").write_text("app_name: Chronicler\n")
    assert is_config_initialized() is True

    monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(tmp_path / "absent.yaml"))
    assert is_config_initialized() is False


def test_set_config_file_override_invalidates_the_cached_settings(tmp_path):
    """
    get_settings() is lru_cached, so an override applied after the first call would
    otherwise have no effect at all.
    """
    explicit = tmp_path / "custom.yaml"
    explicit.write_text("app_name: FromOverride\n")

    assert get_settings().app_name == "Chronicler"

    set_config_file_override(explicit)
    try:
        assert get_settings().app_name == "FromOverride"

        set_config_file_override(None)
        assert get_settings().app_name == "Chronicler"
    finally:
        set_config_file_override(None)


def test_load_settings(tmp_path, monkeypatch):
    def mock_user_config_dir(app_name):
        return str(tmp_path)

    monkeypatch.setattr("chronicler.core.config.user_config_dir", mock_user_config_dir)

    config_file_json = tmp_path / "settings.json"
    workspace_str = str(tmp_path / "test_workspace_json")
    config_file_json.write_text(f'{{"workspace_path": "{workspace_str}"}}')

    settings = Settings()
    assert str(settings.workspace_path) == workspace_str

    config_file_yaml = tmp_path / "settings.yaml"
    workspace_str_yaml = str(tmp_path / "test_workspace_yaml")
    config_file_yaml.write_text(f"workspace_path: {workspace_str_yaml}\n")

    settings = Settings()
    assert str(settings.workspace_path) == workspace_str_yaml


def test_malformed_config_file_logs_warning_instead_of_silent_failure(
    tmp_path, monkeypatch, caplog
):
    def mock_user_config_dir(app_name):
        return str(tmp_path)

    monkeypatch.setattr("chronicler.core.config.user_config_dir", mock_user_config_dir)

    config_file_yaml = tmp_path / "settings.yaml"
    config_file_yaml.write_text("workspace_path: [this is not: valid: yaml")

    with caplog.at_level("WARNING", logger="chronicler.core.config"):
        settings = Settings()

    assert settings.workspace_path is None
    assert any(
        "Failed to parse config file" in record.message and str(config_file_yaml) in record.message
        for record in caplog.records
    )


def test_server_mode_requires_workspace_and_api_key(tmp_path):
    settings = Settings(workspace_path=None, api_key=None)
    assert settings.validate_for_mode("server") is False

    settings.workspace_path = tmp_path
    assert settings.validate_for_mode("server") is False

    settings.api_key = "some-key"
    assert settings.validate_for_mode("server") is True


def test_webclient_mode_requires_server_url_and_api_key(tmp_path):
    settings = Settings(server_url=None, api_key=None)
    assert settings.validate_for_mode("client:web") is False

    settings.server_url = "http://localhost:8000"
    assert settings.validate_for_mode("client:web") is False

    settings.api_key = "some-key"
    assert settings.validate_for_mode("client:web") is True


def test_desktop_mode_requires_either(tmp_path):
    settings = Settings(workspace_path=None, server_url=None, api_key=None)
    assert settings.validate_for_mode("client:desktop") is False

    settings.server_url = ""
    assert settings.validate_for_mode("client:desktop") is False

    settings.workspace_path = tmp_path
    assert settings.validate_for_mode("client:desktop") is True

    settings.workspace_path = None
    settings.server_url = "http://localhost:8000"
    assert settings.validate_for_mode("client:desktop") is False

    settings.api_key = "some-key"
    assert settings.validate_for_mode("client:desktop") is True


def test_unknown_mode_is_always_valid():
    settings = Settings()
    assert settings.validate_for_mode("some-future-mode") is True


class TestNestedSections:
    def test_every_section_defaults_without_configuration(self):
        settings = Settings()

        assert settings.transcription.model_size == "base"
        assert settings.cleaning.drop_hallucinations is True
        assert settings.normalization.target_lufs == -18.0
        assert settings.llm.provider == "none"
        assert settings.ui.locale == "en"
        assert settings.extras.auto_install is False

    def test_a_config_file_predating_the_sections_still_loads(self, isolated_config):
        config_file = isolated_config / ".chronicler_config.yaml"
        config_file.write_text(
            yaml.dump({"app_name": "Legacy", "workspace_path": "/tmp/ws", "dark_mode": False})
        )
        get_settings.cache_clear()

        settings = Settings()

        assert settings.app_name == "Legacy"
        assert settings.dark_mode is False
        assert settings.transcription.language is None

    def test_sections_load_from_a_config_file(self, isolated_config):
        config_file = isolated_config / ".chronicler_config.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "transcription": {"language": "nl", "no_speech_threshold": 0.4},
                    "cleaning": {"hallucination_phrases": ["Ondertiteling door"]},
                    "ui": {"locale": "nl"},
                }
            )
        )
        get_settings.cache_clear()

        settings = Settings()

        assert settings.transcription.language == "nl"
        assert settings.transcription.no_speech_threshold == 0.4
        assert settings.cleaning.hallucination_phrases == ["Ondertiteling door"]
        assert settings.ui.locale == "nl"

    def test_a_partial_section_keeps_the_other_defaults(self, isolated_config):
        config_file = isolated_config / ".chronicler_config.yaml"
        config_file.write_text(yaml.dump({"transcription": {"language": "de"}}))
        get_settings.cache_clear()

        settings = Settings()

        assert settings.transcription.language == "de"
        assert settings.transcription.model_size == "base"
        assert settings.transcription.no_speech_threshold == 0.6

    def test_nested_values_come_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("CHRONICLER_TRANSCRIPTION__LANGUAGE", "fr")
        monkeypatch.setenv("CHRONICLER_LLM__PROVIDER", "openai_compatible")

        settings = Settings()

        assert settings.transcription.language == "fr"
        assert settings.llm.provider == "openai_compatible"

    def test_sections_survive_a_save_and_reload(self, isolated_config, monkeypatch):
        monkeypatch.setattr(
            "chronicler.core.config.user_config_dir", lambda _: str(isolated_config)
        )
        settings = Settings()
        settings.transcription.language = "nl"
        settings.llm.provider = "openai_compatible"
        settings.llm.base_url = "http://localhost:8080/v1"
        settings.llm.model = "qwen3"
        settings.save()
        get_settings.cache_clear()

        reloaded = Settings()

        assert reloaded.transcription.language == "nl"
        assert reloaded.llm.base_url == "http://localhost:8080/v1"
        assert reloaded.llm.is_configured is True

    def test_saved_config_is_plain_yaml_scalars(self, isolated_config, monkeypatch):
        monkeypatch.setattr(
            "chronicler.core.config.user_config_dir", lambda _: str(isolated_config)
        )
        settings = Settings(workspace_path=isolated_config)
        config_file = settings.save()

        raw = yaml.safe_load(config_file.read_text())

        assert isinstance(raw["transcription"], dict)
        assert isinstance(raw["workspace_path"], str)
        assert "!!python" not in config_file.read_text()

    def test_an_invalid_section_value_does_not_make_the_app_unstartable(self, isolated_config):
        config_file = isolated_config / ".chronicler_config.yaml"
        config_file.write_text(yaml.dump({"transcription": {"no_speech_threshold": 99}}))
        get_settings.cache_clear()

        settings = Settings()

        assert settings.transcription.no_speech_threshold == 0.6
