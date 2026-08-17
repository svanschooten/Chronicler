import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from platformdirs import user_config_dir
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

logger = logging.getLogger(__name__)

#: Points Chronicler at one specific config file, bypassing the default search below.
#: Set by `chronicler --config PATH`, or exported directly. Without this, isolating an
#: instance (a throwaway workspace, a smoke test, a second workspace on one machine) meant
#: overriding HOME for the whole process.
CONFIG_FILE_ENV_VAR = "CHRONICLER_CONFIG_FILE"


def config_file_override() -> Path | None:
    """The explicitly requested config file, if there is one."""
    value = os.environ.get(CONFIG_FILE_ENV_VAR)
    return Path(value).expanduser() if value else None


def set_config_file_override(path: Path | str | None) -> None:
    """Requests a specific config file for this process.

    Communicated through the environment rather than passed as an argument because
    `Settings` is constructed by pydantic-settings deep inside `get_settings()`, which
    every entry point calls without any plumbing for it. Setting it also means a
    subprocess inherits the same config, which is what you want for a spawned worker.

    Must be called before the first `get_settings()` - that result is cached.
    """
    if path is None:
        os.environ.pop(CONFIG_FILE_ENV_VAR, None)
    else:
        os.environ[CONFIG_FILE_ENV_VAR] = str(path)
    get_settings.cache_clear()


def _default_config_candidates() -> list[Path]:
    """Where to look when no config file was explicitly requested, in priority order.
    The `.json` entry is legacy and read-only - `save()` always writes YAML."""
    config_dir = Path(user_config_dir("Chronicler"))
    return [
        Path.home() / ".chronicler_config.yaml",
        config_dir / "settings.yaml",
        config_dir / "settings.json",
    ]


def _read_config(path: Path) -> dict[str, Any]:
    try:
        if path.suffix == ".json":
            return json.loads(path.read_text()) or {}
        return yaml.safe_load(path.read_text()) or {}
    except Exception:
        # Warn rather than raise: a corrupt config shouldn't make the app unstartable,
        # and falling back to defaults lets the wizard fix it. Naming the file matters -
        # this used to be a bare `except: pass`.
        logger.warning("Failed to parse config file %s", path, exc_info=True)
        return {}


def resolve_config_file() -> Path | None:
    """The config file Chronicler will actually read, or None if there isn't one yet.

    An explicitly requested file that doesn't exist resolves to None rather than falling
    through to the defaults: `--config` is how a caller isolates an instance, and quietly
    loading the developer's real config instead would defeat the point.
    """
    explicit = config_file_override()
    if explicit is not None:
        if explicit.exists():
            return explicit
        logger.warning("Config file %s does not exist; using defaults", explicit)
        return None

    return next((path for path in _default_config_candidates() if path.exists()), None)


class FileConfigSettingsSource(PydanticBaseSettingsSource):
    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        # Vestigial: __call__ below is fully overridden and never calls this, but the
        # base class declares it @abstractmethod so it must exist with a matching
        # signature (the previous (field_name, field) parameter order didn't match the
        # supertype's (field, field_name), which would have misdirected the two values
        # into each other's parameters had pydantic-settings ever called it directly).
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        path = resolve_config_file()
        return _read_config(path) if path is not None else {}


class Settings(BaseSettings):
    app_name: str = "Chronicler"
    workspace_path: Path | None = None
    server_url: str | None = None
    api_key: str | None = None
    # One of "server", "client:web", "desktop:full_stack", "desktop:thin_client" - set
    # by ConfigWizard once it knows which of the four concrete setups was chosen.
    # Desktop's two sub-modes aren't otherwise distinguishable from settings alone
    # (both can have workspace_path/server_url set at once, e.g. after switching modes
    # once); this records the actual choice rather than re-deriving it.
    mode: str | None = None
    dark_mode: bool = True

    @property
    def config_dir(self) -> Path:
        return Path(user_config_dir(self.app_name))

    def is_workspace_valid(self) -> bool:
        if self.workspace_path is None:
            return False
        if not self.workspace_path.exists() or not self.workspace_path.is_dir():
            return False

        # Check for read/write permissions
        return os.access(self.workspace_path, os.R_OK | os.W_OK)

    def validate_for_mode(self, mode: str) -> bool:
        """Validate if settings are complete for a given mode."""
        if mode == "server":
            return self.workspace_path is not None and bool(self.api_key)
        if mode == "client:web":
            return bool(self.server_url) and bool(self.api_key)
        if mode == "client:desktop":
            # For Full Stack, we need workspace.
            # For Thin Client, we need server_url and API key.
            if self.workspace_path:
                return True
            if self.server_url:
                return bool(self.api_key)
            return False
        return True

    def save(self) -> Path:
        config_file = self.save_path()
        config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(config_file, "w") as f:
            # Round-tripped through JSON first so pydantic serializes Path/enum values
            # into plain YAML scalars rather than Python object tags.
            yaml.dump(json.loads(self.model_dump_json()), f, default_flow_style=False)

        return config_file

    def save_path(self) -> Path:
        """Where `save()` will write.

        An explicitly requested config file wins, even if it doesn't exist yet - a
        `--config` run that changes a setting must persist it where the caller asked,
        not into the developer's real config.
        """
        explicit = config_file_override()
        if explicit is not None:
            return explicit

        # Otherwise update the home config if that's what's in use, and fall back to the
        # platform config directory.
        home_config = Path.home() / ".chronicler_config.yaml"
        if home_config.exists():
            return home_config
        return self.config_dir / "settings.yaml"

    model_config = SettingsConfigDict(env_prefix="CHRONICLER_", env_file=".env", extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            FileConfigSettingsSource(settings_cls),
            dotenv_settings,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def is_config_initialized() -> bool:
    config_file = resolve_config_file()
    if config_file is None:
        return False
    logger.info("Chronicler config loaded from %s", config_file)
    return True
