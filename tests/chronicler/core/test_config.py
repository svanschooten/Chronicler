import json
import os
import stat
import sys
from pathlib import Path

import pytest
import yaml

from chronicler.core.config import (
    CONFIG_FILE_ENV_VAR,
    Mode,
    Settings,
    get_settings,
    is_config_initialized,
    resolve_config_file,
    set_config_file_override,
)
from tests.isolation import isolate_home


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch, tmp_path):
    """Keeps config resolution away from the developer's real configuration."""
    home = tmp_path / "home"
    home.mkdir()
    isolate_home(monkeypatch, home)
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


def test_a_workspace_that_cannot_be_written_is_invalid(tmp_path, monkeypatch):
    """The probe writes a file, so this holds on Windows, where `os.access` would not."""

    def refuse(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr("chronicler.core.workspace_lock.tempfile.TemporaryFile", refuse)

    assert not Settings(workspace_path=tmp_path).is_workspace_valid()


@pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0,
    reason="chmod cannot make a directory unwritable on Windows or for root",
)
def test_read_only_workspace_is_invalid(tmp_path):
    read_only = tmp_path / "readonly"
    read_only.mkdir(mode=0o555)
    try:
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
    config_file_json.write_text(json.dumps({"workspace_path": workspace_str}))

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
    assert settings.validate_for_mode(Mode.SERVER) is False

    settings.workspace_path = tmp_path
    assert settings.validate_for_mode(Mode.SERVER) is False

    settings.api_key = "some-key"
    assert settings.validate_for_mode(Mode.SERVER) is True


def test_full_stack_requires_a_workspace(tmp_path):
    settings = Settings(workspace_path=None, server_url="http://localhost:8000", api_key="k")
    assert settings.validate_for_mode(Mode.FULL_STACK) is False

    settings.workspace_path = tmp_path
    assert settings.validate_for_mode(Mode.FULL_STACK) is True


def test_thin_client_requires_a_server_url_and_api_key(tmp_path):
    settings = Settings(workspace_path=tmp_path, server_url="", api_key=None)
    assert settings.validate_for_mode(Mode.THIN_CLIENT) is False

    settings.server_url = "http://localhost:8000"
    assert settings.validate_for_mode(Mode.THIN_CLIENT) is False

    settings.api_key = "some-key"
    assert settings.validate_for_mode(Mode.THIN_CLIENT) is True


def test_effective_mode_is_the_stored_mode(tmp_path):
    settings = Settings(mode=Mode.THIN_CLIENT, workspace_path=tmp_path)
    assert settings.effective_mode is Mode.THIN_CLIENT


def test_effective_mode_is_inferred_when_none_is_stored(tmp_path):
    assert Settings(server_url="http://server:8000").effective_mode is Mode.THIN_CLIENT
    assert Settings(workspace_path=tmp_path).effective_mode is Mode.FULL_STACK
    both = Settings(workspace_path=tmp_path, server_url="http://server:8000")
    assert both.effective_mode is Mode.FULL_STACK
    assert Settings().effective_mode is Mode.FULL_STACK


def test_a_server_configuration_runs_the_desktop_as_a_full_stack(tmp_path):
    settings = Settings(mode=Mode.SERVER, workspace_path=tmp_path)
    assert settings.effective_mode is Mode.SERVER
    assert settings.desktop_mode is Mode.FULL_STACK


@pytest.mark.parametrize(
    ("stored", "mode"),
    [
        ("desktop:full_stack", Mode.FULL_STACK),
        ("desktop:thin_client", Mode.THIN_CLIENT),
        ("full_stack", Mode.FULL_STACK),
        ("thin_client", Mode.THIN_CLIENT),
        ("server", Mode.SERVER),
        ("client:web", None),
        ("some-future-mode", None),
    ],
)
def test_stored_modes_load(isolated_config, stored, mode):
    (isolated_config / ".chronicler_config.yaml").write_text(yaml.dump({"mode": stored}))

    assert Settings().mode is mode


def test_the_mode_is_saved_as_a_plain_string(isolated_config):
    config_file = Settings(mode=Mode.THIN_CLIENT).save()

    saved = yaml.safe_load(config_file.read_text())
    assert saved["mode"] == "thin_client"


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


class TestSecretsOnSave:
    """Values set through the environment stay out of the config file."""

    def test_an_api_key_from_the_environment_is_not_written(self, isolated_config, monkeypatch):
        monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(isolated_config / "settings.yaml"))
        monkeypatch.setenv("CHRONICLER_API_KEY", "env-secret")
        settings = Settings()
        settings.dark_mode = False

        config_file = settings.save()

        assert "env-secret" not in config_file.read_text()
        assert yaml.safe_load(config_file.read_text())["dark_mode"] is False

    def test_a_nested_secret_from_the_environment_is_not_written(
        self, isolated_config, monkeypatch
    ):
        monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(isolated_config / "settings.yaml"))
        monkeypatch.setenv("CHRONICLER_LLM__API_KEY", "llm-secret")
        settings = Settings()
        settings.llm.model = "qwen3"

        config_file = settings.save()

        saved = yaml.safe_load(config_file.read_text())
        assert "llm-secret" not in config_file.read_text()
        assert saved["llm"]["model"] == "qwen3"

    def test_the_file_keeps_its_own_value_for_an_overridden_setting(
        self, isolated_config, monkeypatch
    ):
        config_file = isolated_config / "settings.yaml"
        config_file.write_text(yaml.dump({"api_key": "file-key"}))
        monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(config_file))
        monkeypatch.setenv("CHRONICLER_API_KEY", "env-secret")

        Settings().save()

        assert yaml.safe_load(config_file.read_text())["api_key"] == "file-key"

    def test_a_key_set_in_the_app_is_still_saved(self, isolated_config, monkeypatch):
        monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(isolated_config / "settings.yaml"))

        config_file = Settings(api_key="typed-in").save()

        assert yaml.safe_load(config_file.read_text())["api_key"] == "typed-in"

    def test_a_secret_leaked_by_an_earlier_save_is_removed(self, isolated_config, monkeypatch):
        """The old save copied the environment's key into the file; this one takes it out."""
        config_file = isolated_config / "settings.yaml"
        config_file.write_text(yaml.dump({"api_key": "env-secret", "dark_mode": False}))
        monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(config_file))
        monkeypatch.setenv("CHRONICLER_API_KEY", "env-secret")

        Settings().save()

        assert "env-secret" not in config_file.read_text()
        assert yaml.safe_load(config_file.read_text())["dark_mode"] is False

    @pytest.mark.skipif(os.name != "posix", reason="file modes are POSIX-only")
    def test_the_file_is_readable_by_its_owner_only(self, isolated_config, monkeypatch):
        config_file = isolated_config / "settings.yaml"
        config_file.write_text("app_name: Chronicler\n")
        config_file.chmod(0o644)
        monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(config_file))

        Settings().save()

        assert stat.S_IMODE(config_file.stat().st_mode) == 0o600


def test_a_saved_web_client_mode_reads_as_unset(isolated_config):
    """The web client is gone; its config must not stop the desktop app from starting."""
    config_file = isolated_config / ".chronicler_config.yaml"
    config_file.write_text(
        yaml.dump({"mode": "client:web", "server_url": "http://server:8000", "api_key": "k"})
    )

    settings = Settings()

    assert settings.mode is None
    assert settings.desktop_mode is Mode.THIN_CLIENT
    assert settings.validate_for_mode(settings.desktop_mode) is True


@pytest.mark.parametrize("stored", ["client:web", "some-future-mode"])
def test_a_mode_read_as_unset_is_warned_about(isolated_config, caplog, stored):
    (isolated_config / ".chronicler_config.yaml").write_text(yaml.dump({"mode": stored}))

    with caplog.at_level("WARNING"):
        Settings()

    assert any(stored in record.getMessage() for record in caplog.records)


def test_a_renamed_mode_loads_without_a_warning(isolated_config, caplog):
    config_file = isolated_config / ".chronicler_config.yaml"
    config_file.write_text(yaml.dump({"mode": "desktop:thin_client"}))

    with caplog.at_level("WARNING"):
        Settings()

    assert not caplog.records


class TestConfigFileEncodingAndAtomicSave:
    def test_a_utf8_config_loads_whatever_the_locale_encoding(self, isolated_config, monkeypatch):
        config_file = isolated_config / "settings.yaml"
        config_file.write_text("app_name: Kroniek \u00e9\u00e8 \u65e5\u672c\n", encoding="utf-8")
        monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(config_file))
        real_read_text = Path.read_text

        def locale_read_text(self, encoding=None, errors=None):
            return real_read_text(self, encoding=encoding or "cp1252", errors=errors)

        monkeypatch.setattr(Path, "read_text", locale_read_text)

        assert get_settings().app_name == "Kroniek \u00e9\u00e8 \u65e5\u672c"

    def test_non_ascii_text_is_saved_as_utf8(self, isolated_config, monkeypatch):
        config_file = isolated_config / "settings.yaml"
        monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(config_file))

        Settings(app_name="Kroniek \u00e9 \u65e5\u672c").save()

        text = config_file.read_bytes().decode("utf-8")
        assert "Kroniek \u00e9 \u65e5\u672c" in text

    def test_a_failed_write_leaves_the_existing_file_untouched(self, isolated_config, monkeypatch):
        config_file = isolated_config / "settings.yaml"
        config_file.write_text("app_name: Before\n", encoding="utf-8")
        monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(config_file))

        def crash(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr("chronicler.core.config.yaml.dump", crash)

        with pytest.raises(OSError):
            Settings(app_name="After").save()

        assert config_file.read_text(encoding="utf-8") == "app_name: Before\n"
        assert [p.name for p in config_file.parent.iterdir()] == ["settings.yaml"]

    def test_an_unparseable_file_is_backed_up_before_it_is_replaced(
        self, isolated_config, monkeypatch
    ):
        config_file = isolated_config / "settings.yaml"
        broken = "app_name: [unclosed\nnote: keep me\n"
        config_file.write_text(broken, encoding="utf-8")
        monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(config_file))

        Settings(app_name="Fresh").save()

        assert (isolated_config / "settings.yaml.bak").read_text(encoding="utf-8") == broken
        assert yaml.safe_load(config_file.read_text(encoding="utf-8"))["app_name"] == "Fresh"

    def test_a_readable_file_is_not_backed_up(self, isolated_config, monkeypatch):
        config_file = isolated_config / "settings.yaml"
        config_file.write_text("app_name: Fine\n", encoding="utf-8")
        monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(config_file))

        Settings().save()

        assert not (isolated_config / "settings.yaml.bak").exists()

    def test_an_ansi_config_from_an_older_editor_still_loads(self, isolated_config, monkeypatch):
        """Notepad's old "ANSI" is the Windows code page. That loaded before UTF-8 reads."""
        config_file = isolated_config / "settings.yaml"
        config_file.write_bytes("app_name: Café\napi_key: kept\n".encode("cp1252"))
        monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(config_file))
        monkeypatch.setattr(
            "chronicler.core.config.locale.getpreferredencoding", lambda _: "cp1252"
        )

        settings = get_settings()

        assert settings.app_name == "Café"
        assert settings.api_key == "kept"

    def test_a_utf8_file_with_a_byte_order_mark_loads(self, isolated_config, monkeypatch):
        config_file = isolated_config / "settings.yaml"
        config_file.write_bytes("app_name: Café\n".encode("utf-8-sig"))
        monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(config_file))

        assert get_settings().app_name == "Café"

    @pytest.mark.skipif(os.name != "posix", reason="file modes are POSIX-only")
    def test_the_backup_is_readable_by_its_owner_only(self, isolated_config, monkeypatch):
        config_file = isolated_config / "settings.yaml"
        config_file.write_text("api_key: [unclosed\n", encoding="utf-8")
        config_file.chmod(0o644)
        monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(config_file))

        Settings().save()

        backup = isolated_config / "settings.yaml.bak"
        assert stat.S_IMODE(backup.stat().st_mode) == 0o600

    @pytest.mark.skipif(os.name != "posix", reason="symlinks need privileges on Windows")
    def test_a_symlinked_config_is_written_where_it_points(self, isolated_config, monkeypatch):
        real = isolated_config / "dotfiles" / "chronicler.yaml"
        real.parent.mkdir()
        real.write_text("app_name: Linked\n", encoding="utf-8")
        link = isolated_config / "settings.yaml"
        link.symlink_to(real)
        monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(link))

        Settings(app_name="Updated").save()

        assert link.is_symlink()
        assert yaml.safe_load(real.read_text(encoding="utf-8"))["app_name"] == "Updated"
