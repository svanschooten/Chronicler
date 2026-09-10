import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from platformdirs import user_config_dir
from pydantic import Field, ValidationError
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

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


class Settings(BaseSettings):
    app_name: str = "Chronicler"
    workspace_path: Path | None = None
    server_url: str | None = None
    api_key: str | None = None
    mode: str | None = None
    dark_mode: bool = True

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

    def validate_for_mode(self, mode: str) -> bool:
        """Validate if settings are complete for a given mode."""
        if mode == "server":
            return self.workspace_path is not None and bool(self.api_key)
        if mode == "client:web":
            return bool(self.server_url) and bool(self.api_key)
        if mode == "client:desktop":
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
            yaml.dump(json.loads(self.model_dump_json()), f, default_flow_style=False)

        return config_file

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


def reload_settings() -> Settings:
    """Reload settings from disk after wizard saves them."""
    get_settings.cache_clear()
    return get_settings()


def is_config_initialized() -> bool:
    config_file = resolve_config_file()
    if config_file is None:
        return False
    logger.info("Chronicler config loaded from %s", config_file)
    return True
