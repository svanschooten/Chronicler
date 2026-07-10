import os
from functools import lru_cache
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from platformdirs import user_config_dir

class Settings(BaseSettings):
    app_name: str = "Chronicler"
    workspace_path: Optional[Path] = None
    
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

    model_config = SettingsConfigDict(
        env_prefix="CHRONICLER_",
        env_file=".env",
        extra="ignore"
    )

@lru_cache
def get_settings() -> Settings:
    return Settings()
