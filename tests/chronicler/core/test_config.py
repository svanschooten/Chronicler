from chronicler.core.config import Settings, get_settings


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
    import yaml

    with open(config_file) as f:
        data = yaml.safe_load(f)
        assert data["workspace_path"] == str(workspace)


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
