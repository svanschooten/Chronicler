from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from chronicler.core.config import Settings
from chronicler.core.wizard import ConfigWizard


@pytest.fixture
def mock_settings(tmp_path):
    with patch("chronicler.core.config.user_config_dir", return_value=str(tmp_path)):
        settings = Settings()
        yield settings

def test_wizard_full_stack(tmp_path):
    config_dir_patch = patch(
        "chronicler.core.config.user_config_dir",
        side_effect=lambda name: str(tmp_path / name),
    )
    with config_dir_patch, \
         patch("builtins.input", side_effect=["1", str(tmp_path / "workspace"), "1"]), \
         patch("builtins.print"):
        
        wizard = ConfigWizard()
        wizard.run()
        
        # Verify settings were saved
        settings_file = tmp_path / "Chronicler" / "settings.yaml"
        assert settings_file.exists()
        
        from chronicler.core.config import Settings
        # We need to bypass the lru_cache for get_settings if we were using it, 
        # but here we can just check the file or create a new Settings object
        saved_settings = Settings()
        assert saved_settings.workspace_path == tmp_path / "workspace"
        assert saved_settings.server_url is None
        assert saved_settings.api_key is not None
        assert len(saved_settings.api_key) > 0

def test_wizard_full_stack_manual_api_key(tmp_path):
    config_dir_patch = patch(
        "chronicler.core.config.user_config_dir",
        side_effect=lambda name: str(tmp_path / name),
    )
    with config_dir_patch, \
         patch(
             "builtins.input",
             side_effect=["1", str(tmp_path / "workspace"), "2", "my-custom-key"],
         ), \
         patch("builtins.print"):
        
        wizard = ConfigWizard()
        wizard.run()
        
        saved_settings = Settings()
        assert saved_settings.workspace_path == tmp_path / "workspace"
        assert saved_settings.api_key == "my-custom-key"

def test_wizard_thin_client(tmp_path):
    config_dir_patch = patch(
        "chronicler.core.config.user_config_dir",
        side_effect=lambda name: str(tmp_path / name),
    )
    with config_dir_patch, \
         patch("builtins.input", side_effect=["2", "http://remote:8000", "secret-key"]), \
         patch("builtins.print"):
        
        wizard = ConfigWizard()
        wizard.run()
        
        settings_file = tmp_path / "Chronicler" / "settings.yaml"
        assert settings_file.exists()
        
        saved_settings = Settings()
        assert saved_settings.server_url == "http://remote:8000"
        assert saved_settings.api_key == "secret-key"
        assert saved_settings.workspace_path is None

def test_wizard_reports_correct_path(tmp_path):
    from io import StringIO
    
    # We want to catch the output of print
    out = StringIO()
    config_dir_patch = patch(
        "chronicler.core.config.user_config_dir",
        side_effect=lambda name: str(tmp_path / name),
    )
    with config_dir_patch, \
         patch("builtins.input", side_effect=["1", str(tmp_path / "workspace"), "3"]), \
         patch("sys.stdout", new=out):
        
        wizard = ConfigWizard()
        wizard.run()
        
        output = out.getvalue()
        expected_path = tmp_path / "Chronicler" / "settings.yaml"
        assert f"Configuration saved to {expected_path}" in output
        assert ".json" not in output

def test_wizard_server(tmp_path):
    config_dir_patch = patch(
        "chronicler.core.config.user_config_dir",
        side_effect=lambda name: str(tmp_path / name),
    )
    with config_dir_patch, \
         patch("builtins.input", side_effect=["3", str(tmp_path / "srv-workspace"), "1"]), \
         patch("builtins.print"):
        
        wizard = ConfigWizard()
        wizard.run()
        
        saved_settings = Settings()
        assert saved_settings.workspace_path == tmp_path / "srv-workspace"
        assert saved_settings.api_key is not None

def test_wizard_web_client(tmp_path):
    config_dir_patch = patch(
        "chronicler.core.config.user_config_dir",
        side_effect=lambda name: str(tmp_path / name),
    )
    with config_dir_patch, \
         patch("builtins.input", side_effect=["4", "http://server:8000", "web-key"]), \
         patch("builtins.print"):
        
        wizard = ConfigWizard()
        wizard.run()
        
        saved_settings = Settings()
        assert saved_settings.server_url == "http://server:8000"
        assert saved_settings.api_key == "web-key"


def test_api_key_step_generates_on_empty_input():
    settings = Settings()
    # Option 2 is "Enter an existing API key"
    # We provide "2" then "" (empty enter)
    inputs = ["2", ""]

    with patch("builtins.input", side_effect=inputs), \
         patch("sys.stdout", new=StringIO()) as fake_out:
        from chronicler.core.wizard import ApiKeyStep
        step = ApiKeyStep()
        step.run(settings)

        assert settings.api_key is not None
        assert len(settings.api_key) == 43  # secrets.token_urlsafe(32) produces ~43 chars
        assert "Generated API key:" in fake_out.getvalue()


def test_remote_server_step_generates_on_empty_api_key():
    settings = Settings()
    # RemoteServerStep asks for URL then API key
    # We provide "http://localhost:8000" then ""
    inputs = ["http://localhost:8000", ""]

    with patch("builtins.input", side_effect=inputs), \
         patch("sys.stdout", new=StringIO()) as fake_out:
        from chronicler.core.wizard import RemoteServerStep
        step = RemoteServerStep()
        step.run(settings)

        assert settings.server_url == "http://localhost:8000"
        assert settings.api_key is not None
        assert len(settings.api_key) == 43
        assert "No API key provided. Generated:" in fake_out.getvalue()

def test_server_mode_requires_workspace_and_api_key(tmp_path):
    # Setup settings
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
    settings = Settings(workspace_path=None, server_url=None)
    assert settings.validate_for_mode("client:desktop") is False
    
    # Reject empty string
    settings.server_url = ""
    assert settings.validate_for_mode("client:desktop") is False
    
    settings.workspace_path = tmp_path
    assert settings.validate_for_mode("client:desktop") is True
    
    settings.workspace_path = None
    settings.server_url = "http://localhost:8000"
    assert settings.validate_for_mode("client:desktop") is True

@patch("chronicler.core.wizard.WorkspaceStep.run")
@patch("chronicler.core.wizard.ApiKeyStep.run")
def test_wizard_run_server_mode(mock_api, mock_ws, tmp_path):
    with patch("chronicler.core.config.user_config_dir", return_value=str(tmp_path)):
        settings = Settings(workspace_path=None)
        wizard = ConfigWizard(settings=settings)
        wizard.run(mode="server")
        
    mock_ws.assert_called_once()
    mock_api.assert_called_once()

@patch("chronicler.core.wizard.RemoteServerStep.run")
def test_wizard_run_webclient_mode(mock_remote, tmp_path):
    with patch("chronicler.core.config.user_config_dir", return_value=str(tmp_path)):
        settings = Settings(server_url=None)
        wizard = ConfigWizard(settings=settings)
        wizard.run(mode="client:web")
        
    mock_remote.assert_called_once()

@patch("chronicler.core.wizard.ConfigWizard._show_main_choice")
def test_wizard_run_desktop_mode_missing(mock_choice, tmp_path):
    with patch("chronicler.core.config.user_config_dir", return_value=str(tmp_path)):
        settings = Settings(workspace_path=None, server_url=None)
        wizard = ConfigWizard(settings=settings)
        wizard.run(mode="client:desktop")
        
    mock_choice.assert_called_once()

@patch("chronicler.core.wizard.run_wizard")
@patch("chronicler.core.config.is_config_initialized", return_value=True)
@patch("chronicler.core.config.get_settings")
def test_main_checks_validity(mock_get_settings, mock_is_init, mock_run_wizard):
    import sys

    from chronicler.__main__ import main
    
    # Mock settings that are INVALID for server mode
    mock_settings = MagicMock(spec=Settings)
    mock_settings.validate_for_mode.return_value = False
    mock_get_settings.return_value = mock_settings
    
    with patch.object(sys, "argv", ["chronicler", "server"]), \
         patch("chronicler.__main__.server_main"):
        main()
        
    mock_settings.validate_for_mode.assert_called_with("server")
    mock_run_wizard.assert_called_with(mode="server")

@patch("chronicler.core.wizard.run_wizard")
@patch("chronicler.core.config.is_config_initialized", return_value=True)
@patch("chronicler.core.config.get_settings")
def test_main_skips_wizard_if_valid(mock_get_settings, mock_is_init, mock_run_wizard):
    import sys

    from chronicler.__main__ import main

    # Mock settings that are VALID for server mode
    mock_settings = MagicMock(spec=Settings)
    mock_settings.validate_for_mode.return_value = True
    mock_get_settings.return_value = mock_settings

    with patch.object(sys, "argv", ["chronicler", "server"]), \
         patch("chronicler.__main__.server_main"):
        main()

    mock_settings.validate_for_mode.assert_called_with("server")
    mock_run_wizard.assert_not_called()


def test_wizard_skips_satisfied_steps(tmp_path):
    with patch("chronicler.core.config.user_config_dir", return_value=str(tmp_path)):
        # Simulate previous run that set api_key
        settings = Settings(api_key="existing-key", workspace_path=None)
        wizard = ConfigWizard(settings=settings)

        # Run wizard for 'server' mode.
        # 'server' mode runs WorkspaceStep and ApiKeyStep.
        # It should only run WorkspaceStep because api_key is already set.

        with patch("chronicler.core.wizard.WorkspaceStep.run") as mock_ws, \
             patch("chronicler.core.wizard.ApiKeyStep.run") as mock_api:
            wizard.run(mode="server")

            mock_ws.assert_called_once()
            mock_api.assert_not_called()


def test_wizard_desktop_choice_skips_satisfied_steps(tmp_path):
    with patch("chronicler.core.config.user_config_dir", return_value=str(tmp_path)):
        # Simulate previous run that set api_key
        settings = Settings(api_key="existing-key", workspace_path=None, server_url=None)
        wizard = ConfigWizard(settings=settings)

        # Run wizard for 'client:desktop' mode.
        # User will choose '1' (Full Stack).
        # It should run WorkspaceStep but skip ApiKeyStep.

        with patch("builtins.input", return_value="1"), \
             patch("chronicler.core.wizard.WorkspaceStep.run") as mock_ws, \
             patch("chronicler.core.wizard.ApiKeyStep.run") as mock_api:
            wizard.run(mode="client:desktop")

            mock_ws.assert_called_once()
            mock_api.assert_not_called()
