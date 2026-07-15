import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


class JsonConfigSettingsSource(PydanticBaseSettingsSource):
    def get_field_value(self, field_name: str, field: Any) -> tuple[Any, str, bool]:
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        config_dir = Path(user_config_dir("Chronicler"))
        config_file = config_dir / "settings.json"
        if config_file.exists():
            try:
                return json.loads(config_file.read_text())
            except Exception:
                return {}
        return {}


class Settings(BaseSettings):
    app_name: str = "Chronicler"
    workspace_path: Path | None = None

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

    def save(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        config_file = self.config_dir / "settings.json"
        with open(config_file, "w") as f:
            f.write(self.model_dump_json(indent=4))

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
            JsonConfigSettingsSource(settings_cls),
            dotenv_settings,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
