import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from platformdirs import user_config_dir
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

logger = logging.getLogger(__name__)


class FileConfigSettingsSource(PydanticBaseSettingsSource):
    def get_field_value(self, field_name: str, field: Any) -> tuple[Any, str, bool]:
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        # Priority 1: ~/.chronicler_config.yaml
        home_config = Path.home() / ".chronicler_config.yaml"
        if home_config.exists():
            try:
                return yaml.safe_load(home_config.read_text()) or {}
            except Exception:
                pass

        # Priority 2: Platform specific settings.yaml
        config_dir = Path(user_config_dir("Chronicler"))
        config_file_yaml = config_dir / "settings.yaml"
        if config_file_yaml.exists():
            try:
                return yaml.safe_load(config_file_yaml.read_text()) or {}
            except Exception:
                pass

        # Priority 3: Platform specific settings.json (legacy)
        config_file_json = config_dir / "settings.json"
        if config_file_json.exists():
            try:
                return json.loads(config_file_json.read_text()) or {}
            except Exception:
                pass

        return {}


class Settings(BaseSettings):
    app_name: str = "Chronicler"
    workspace_path: Path | None = None
    server_url: str | None = None
    api_key: str | None = None

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
        home_config = Path.home() / ".chronicler_config.yaml"
        # If home config exists, we update it. Otherwise use platform dir.
        if home_config.exists():
            config_file = home_config
        else:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            config_file = self.config_dir / "settings.yaml"

        with open(config_file, "w") as f:
            # Convert to dict and then to yaml
            yaml.dump(json.loads(self.model_dump_json()), f, default_flow_style=False)

        return config_file

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
    home_config = Path.home() / ".chronicler_config.yaml"

    if home_config.exists():
        logger.info("Chronicler config loaded from %s", home_config)
        return True

    config_dir = Path(user_config_dir("Chronicler"))
    if (config_dir / "settings.yaml").exists():
        logger.info("Chronicler config loaded from %s", (config_dir / "settings.yaml"))
        return True
    if (config_dir / "settings.json").exists():
        logger.info("Chronicler config loaded from %s", (config_dir / "settings.json"))
        return True

    return False
