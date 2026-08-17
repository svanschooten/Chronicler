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
    """Keeps config resolution away from the developer's real configuration.

    Redirecting HOME covers both default locations at once - `Path.home() /
    ".chronicler_config.yaml"` and, on Linux, `user_config_dir()` underneath it. Without
    this, every test here that asserted a default (`workspace_path is None`) passed or
    failed depending on whether the machine running it happened to have a real
    `~/.chronicler_config.yaml`; only `user_config_dir` was ever isolated.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv(CONFIG_FILE_ENV_VAR, raising=False)
    get_settings.cache_clear()
    yield home
    get_settings.cache_clear()


def test_default_settings(monkeypatch, tmp_path):
    # Mock user_config_dir to a clean temp path
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
    # Test with non-existent directory
    non_existent = tmp_path / "missing"
    settings = Settings(workspace_path=non_existent)
    assert not settings.is_workspace_valid()

    # Test with existing directory
    existing = tmp_path / "exists"
    existing.mkdir()
    settings = Settings(workspace_path=existing)
    assert settings.is_workspace_valid()

    # Test with read-only directory (if possible to test on this OS)
    # On linux we can change mode
    try:
        read_only = tmp_path / "readonly"
        read_only.mkdir(mode=0o555)  # Read and execute, no write
        settings = Settings(workspace_path=read_only)
        assert not settings.is_workspace_valid()
    finally:
        read_only.chmod(0o777)  # Clean up so it can be deleted


def test_save_settings(tmp_path, monkeypatch):
    # Mock config_dir to a temp path
    monkeypatch.setattr(Settings, "config_dir", tmp_path)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    settings = Settings(workspace_path=workspace)
    settings.save()

    config_file = tmp_path / "settings.yaml"
    assert config_file.exists()

    # Verify content
    with open(config_file) as f:
        data = yaml.safe_load(f)
        assert data["workspace_path"] == str(workspace)


# -- explicit config file location ---------------------------------------------


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
    """The whole point of --config is isolating an instance. Quietly loading the
    developer's real config instead would defeat it - and in a smoke test would point a
    throwaway run at their real workspace."""
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
    """A --config run that changes a setting must persist it where the caller asked, not
    into the default location."""
    explicit = tmp_path / "elsewhere" / "custom.yaml"
    monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(explicit))
    settings = Settings(app_name="Chronicler", dark_mode=False)

    written = settings.save()

    # Written even though it did not exist beforehand, parent directory and all.
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
    """get_settings() is lru_cached, so an override applied after the first call would
    otherwise have no effect at all."""
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
    # Mock user_config_dir to return tmp_path
    def mock_user_config_dir(app_name):
        return str(tmp_path)

    monkeypatch.setattr("chronicler.core.config.user_config_dir", mock_user_config_dir)

    # Test JSON loading (legacy)
    config_file_json = tmp_path / "settings.json"
    workspace_str = str(tmp_path / "test_workspace_json")
    config_file_json.write_text(f'{{"workspace_path": "{workspace_str}"}}')

    settings = Settings()
    assert str(settings.workspace_path) == workspace_str

    # Test YAML loading (current)
    # Clear lru_cache for Settings if needed, but Settings() creates a new instance each time,
    # it's get_settings() that is cached.
    config_file_yaml = tmp_path / "settings.yaml"
    workspace_str_yaml = str(tmp_path / "test_workspace_yaml")
    config_file_yaml.write_text(f"workspace_path: {workspace_str_yaml}\n")

    # Priority is YAML, so it should pick the yaml one now if both exist
    # (actually in my impl it's Priority 2 platform yaml)
    # Wait, in my impl it's Priority 2: settings.yaml, Priority 3: settings.json
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

    # Malformed config falls back to defaults rather than crashing...
    assert settings.workspace_path is None
    # ...but it must not fail silently: a warning naming the broken file is logged.
    assert any(
        "Failed to parse config file" in record.message and str(config_file_yaml) in record.message
        for record in caplog.records
    )


def test_server_mode_requires_workspace_and_api_key(tmp_path):
    settings = Settings(workspace_path=None, api_key=None)
    assert settings.validate_for_mode("server") is False

    settings.workspace_path = tmp_path
    assert settings.validate_for_mode("server") is False  # Missing API key

    settings.api_key = "some-key"
    assert settings.validate_for_mode("server") is True


def test_webclient_mode_requires_server_url_and_api_key(tmp_path):
    settings = Settings(server_url=None, api_key=None)
    assert settings.validate_for_mode("client:web") is False

    settings.server_url = "http://localhost:8000"
    assert settings.validate_for_mode("client:web") is False  # Missing API key

    settings.api_key = "some-key"
    assert settings.validate_for_mode("client:web") is True


def test_desktop_mode_requires_either(tmp_path):
    settings = Settings(workspace_path=None, server_url=None, api_key=None)
    assert settings.validate_for_mode("client:desktop") is False

    # Reject empty string
    settings.server_url = ""
    assert settings.validate_for_mode("client:desktop") is False

    # A local workspace is enough on its own - full stack needs no key.
    settings.workspace_path = tmp_path
    assert settings.validate_for_mode("client:desktop") is True

    # Without a workspace it's a thin client, which does need a key. This assertion used
    # to expect True and passed only because `Settings()` picked up an `api_key` from the
    # developer's real config file - the test never set one.
    settings.workspace_path = None
    settings.server_url = "http://localhost:8000"
    assert settings.validate_for_mode("client:desktop") is False

    settings.api_key = "some-key"
    assert settings.validate_for_mode("client:desktop") is True


def test_unknown_mode_is_always_valid():
    # validate_for_mode falls through to True for any mode string it doesn't
    # recognize, rather than rejecting unknown modes outright.
    settings = Settings()
    assert settings.validate_for_mode("some-future-mode") is True
