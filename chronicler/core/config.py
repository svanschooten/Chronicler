import json
import logging
import os
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from platformdirs import user_config_dir
from pydantic import Field, ValidationError, field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from chronicler.core.config_sections import (
    CleaningSettings,
    ExtrasSettings,
    LlmSettings,
    NormalizationSettings,
    SummarySettings,
    TranscriptionSettings,
    UiSettings,
)

SECTION_MODELS: dict[str, type] = {
    "transcription": TranscriptionSettings,
    "cleaning": CleaningSettings,
    "normalization": NormalizationSettings,
    "llm": LlmSettings,
    "summary": SummarySettings,
    "ui": UiSettings,
    "extras": ExtrasSettings,
}

logger = logging.getLogger(__name__)

CONFIG_FILE_ENV_VAR = "CHRONICLER_CONFIG_FILE"


def config_file_override() -> Path | None:
    """The explicitly requested config file, if there is one."""
    value = os.environ.get(CONFIG_FILE_ENV_VAR)
    return Path(value).expanduser() if value else None


def set_config_file_override(path: Path | str | None) -> None:
    """Requests a specific config file for this process."""
    if path is None:
        os.environ.pop(CONFIG_FILE_ENV_VAR, None)
    else:
        os.environ[CONFIG_FILE_ENV_VAR] = str(path)
    get_settings.cache_clear()


def _default_config_candidates() -> list[Path]:
    """Where to look when no config file was explicitly requested, in priority order."""
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
        logger.warning("Failed to parse config file %s", path, exc_info=True)
        return {}


def resolve_config_file() -> Path | None:
    """The config file Chronicler will actually read, or None if there isn't one yet."""
    explicit = config_file_override()
    if explicit is not None:
        if explicit.exists():
            return explicit
        logger.warning("Config file %s does not exist; using defaults", explicit)
        return None

    return next((path for path in _default_config_candidates() if path.exists()), None)


def _drop_invalid_sections(raw: dict[str, Any]) -> dict[str, Any]:
    """Replaces any section that fails validation with its defaults, warning about it."""
    cleaned = dict(raw)
    for name, model in SECTION_MODELS.items():
        if name not in cleaned:
            continue
        try:
            model(**(cleaned[name] or {}))
        except (ValidationError, TypeError):
            logger.warning("Ignoring invalid '%s' configuration section; using defaults", name)
            cleaned.pop(name)
    return cleaned


class FileConfigSettingsSource(PydanticBaseSettingsSource):
    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        path = resolve_config_file()
        return _drop_invalid_sections(_read_config(path)) if path is not None else {}


def _deep_merge(target: dict[str, Any], extra: dict[str, Any]) -> None:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value


def _keep_file_values(
    values: dict[str, Any], environment: dict[str, Any], existing: dict[str, Any]
) -> None:
    """
    Replaces every value the environment set with what the file already had, or drops it
    when the file had nothing, recursing into sections such as `llm`.

    A file value equal to the environment's is dropped too: that is how an earlier
    version's save leaked environment secrets into the file, and the environment still
    supplies it.
    """
    for key, env_value in environment.items():
        current = values.get(key)
        if isinstance(env_value, dict) and isinstance(current, dict):
            previous = existing.get(key)
            _keep_file_values(current, env_value, previous if isinstance(previous, dict) else {})
        elif key in existing and existing[key] != env_value:
            values[key] = existing[key]
        else:
            values.pop(key, None)


class Mode(StrEnum):
    """How this installation runs. The one vocabulary for the CLI, the config and the UI."""

    FULL_STACK = "full_stack"
    THIN_CLIENT = "thin_client"
    SERVER = "server"


# Spellings earlier versions saved. `client:web` went with the web client and reads as
# unset, so the mode is inferred from the server URL and workspace.
LEGACY_MODES: dict[str, Mode | None] = {
    "desktop:full_stack": Mode.FULL_STACK,
    "desktop:thin_client": Mode.THIN_CLIENT,
    "client:web": None,
}


class Settings(BaseSettings):
    app_name: str = "Chronicler"
    workspace_path: Path | None = None
    server_url: str | None = None
    api_key: str | None = None
    mode: Mode | None = None
    dark_mode: bool = True

    @field_validator("mode", mode="before")
    @classmethod
    def _read_stored_mode(cls, mode: Any) -> Any:
        """Accepts the old spellings, and reads a mode it does not know as unset."""
        if mode is None or isinstance(mode, Mode):
            return mode
        if mode in LEGACY_MODES:
            return LEGACY_MODES[mode]
        try:
            return Mode(mode)
        except ValueError:
            logger.warning("Ignoring unknown mode %r in the config", mode)
            return None

    transcription: TranscriptionSettings = Field(default_factory=TranscriptionSettings)
    cleaning: CleaningSettings = Field(default_factory=CleaningSettings)
    normalization: NormalizationSettings = Field(default_factory=NormalizationSettings)
    llm: LlmSettings = Field(default_factory=LlmSettings)
    summary: SummarySettings = Field(default_factory=SummarySettings)
    ui: UiSettings = Field(default_factory=UiSettings)
    extras: ExtrasSettings = Field(default_factory=ExtrasSettings)

    @property
    def config_dir(self) -> Path:
        return Path(user_config_dir(self.app_name))

    def is_workspace_valid(self) -> bool:
        if self.workspace_path is None:
            return False
        if not self.workspace_path.exists() or not self.workspace_path.is_dir():
            return False

        return os.access(self.workspace_path, os.R_OK | os.W_OK)

    @property
    def effective_mode(self) -> Mode:
        """The stored mode, or the one a config saved without it describes."""
        if self.mode is not None:
            return self.mode
        if self.server_url and not self.workspace_path:
            return Mode.THIN_CLIENT
        return Mode.FULL_STACK

    @property
    def desktop_mode(self) -> Mode:
        """
        The mode the desktop app runs in. A server's configuration opens its workspace as a
        full stack.
        """
        mode = self.effective_mode
        return Mode.FULL_STACK if mode is Mode.SERVER else mode

    def validate_for_mode(self, mode: Mode) -> bool:
        """Whether the settings are complete enough to run in a given mode."""
        if mode is Mode.SERVER:
            return self.workspace_path is not None and bool(self.api_key)
        if mode is Mode.THIN_CLIENT:
            return bool(self.server_url) and bool(self.api_key)
        return self.workspace_path is not None

    def save(self) -> Path:
        """
        Writes the configuration, leaving out anything set through the environment or a
        `.env` file: those are usually secrets, and saving them would copy them into a
        plain file the first time anything changed. The file keeps whatever it already
        had for those settings. See docs/configuration.md.
        """
        config_file = self.save_path()
        config_file.parent.mkdir(parents=True, exist_ok=True)

        values = json.loads(self.model_dump_json())
        existing = _read_config(config_file) if config_file.exists() else {}
        _keep_file_values(values, self._environment_values(), existing)

        # Owner-only, before anything is written: the file can hold API keys. A new file is
        # created 600; an existing one is restricted first. Windows has no such mode bits.
        if os.name == "posix" and config_file.exists():
            config_file.chmod(0o600)
        descriptor = os.open(config_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w") as f:
            yaml.dump(values, f, default_flow_style=False)

        return config_file

    @classmethod
    def _environment_values(cls) -> dict[str, Any]:
        """What the environment and `.env` set, nested the way the settings are."""
        values: dict[str, Any] = {}
        for source in (DotEnvSettingsSource(cls), EnvSettingsSource(cls)):
            _deep_merge(values, source())
        return values

    def save_path(self) -> Path:
        """Where `save()` will write."""
        explicit = config_file_override()
        if explicit is not None:
            return explicit

        home_config = Path.home() / ".chronicler_config.yaml"
        if home_config.exists():
            return home_config
        return self.config_dir / "settings.yaml"

    model_config = SettingsConfigDict(
        env_prefix="CHRONICLER_",
        env_file=".env",
        extra="ignore",
        env_nested_delimiter="__",
        protected_namespaces=(),
    )

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
