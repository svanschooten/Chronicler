import os
from pathlib import Path
import pytest
from chronicler.core.config import Settings, get_settings

def test_default_settings():
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
        read_only.mkdir(mode=0o555) # Read and execute, no write
        settings = Settings(workspace_path=read_only)
        assert not settings.is_workspace_valid()
    finally:
        read_only.chmod(0o777) # Clean up so it can be deleted

def test_save_settings(tmp_path, monkeypatch):
    # Mock config_dir to a temp path
    monkeypatch.setattr(Settings, "config_dir", tmp_path)
    
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    settings = Settings(workspace_path=workspace)
    settings.save()
    
    config_file = tmp_path / "settings.json"
    assert config_file.exists()
    
    # Verify content
    import json
    with open(config_file, "r") as f:
        data = json.load(f)
        assert data["workspace_path"] == str(workspace)
