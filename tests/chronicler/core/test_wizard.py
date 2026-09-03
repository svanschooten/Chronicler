from io import StringIO
from unittest.mock import patch

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
    with (
        config_dir_patch,
        patch("builtins.input", side_effect=["1", "1", str(tmp_path / "workspace"), "1"]),
        patch("builtins.print"),
    ):
        wizard = ConfigWizard()
        wizard.run()

        settings_file = tmp_path / "Chronicler" / "settings.yaml"
        assert settings_file.exists()

        saved_settings = Settings()
        assert saved_settings.workspace_path == tmp_path / "workspace"
        assert saved_settings.server_url is None
        assert saved_settings.api_key is not None
        assert len(saved_settings.api_key) > 0
        assert saved_settings.mode == "desktop:full_stack"


def test_wizard_full_stack_manual_api_key(tmp_path):
    config_dir_patch = patch(
        "chronicler.core.config.user_config_dir",
        side_effect=lambda name: str(tmp_path / name),
    )
    with (
        config_dir_patch,
        patch(
            "builtins.input",
            side_effect=["1", "1", str(tmp_path / "workspace"), "2", "my-custom-key"],
        ),
        patch("builtins.print"),
    ):
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
    with (
        config_dir_patch,
        patch("builtins.input", side_effect=["1", "2", "http://remote:8000", "secret-key"]),
        patch("builtins.print"),
    ):
        wizard = ConfigWizard()
        wizard.run()

        settings_file = tmp_path / "Chronicler" / "settings.yaml"
        assert settings_file.exists()

        saved_settings = Settings()
        assert saved_settings.server_url == "http://remote:8000"
        assert saved_settings.api_key == "secret-key"
        assert saved_settings.workspace_path is None
        assert saved_settings.mode == "desktop:thin_client"


def test_wizard_reports_correct_path(tmp_path):
    out = StringIO()
    config_dir_patch = patch(
        "chronicler.core.config.user_config_dir",
        side_effect=lambda name: str(tmp_path / name),
    )
    with (
        config_dir_patch,
        patch("builtins.input", side_effect=["1", "1", str(tmp_path / "workspace"), "3"]),
        patch("sys.stdout", new=out),
    ):
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
    with (
        config_dir_patch,
        patch("builtins.input", side_effect=["1", "3", str(tmp_path / "srv-workspace"), "1"]),
        patch("builtins.print"),
    ):
        wizard = ConfigWizard()
        wizard.run()

        saved_settings = Settings()
        assert saved_settings.workspace_path == tmp_path / "srv-workspace"
        assert saved_settings.api_key is not None
        assert saved_settings.mode == "server"


def test_wizard_web_client(tmp_path):
    config_dir_patch = patch(
        "chronicler.core.config.user_config_dir",
        side_effect=lambda name: str(tmp_path / name),
    )
    with (
        config_dir_patch,
        patch("builtins.input", side_effect=["1", "4", "http://server:8000", "web-key"]),
        patch("builtins.print"),
    ):
        wizard = ConfigWizard()
        wizard.run()

        saved_settings = Settings()
        assert saved_settings.server_url == "http://server:8000"
        assert saved_settings.api_key == "web-key"
        assert saved_settings.mode == "client:web"


def test_api_key_step_generates_on_empty_input():
    settings = Settings()
    inputs = ["2", ""]

    with (
        patch("builtins.input", side_effect=inputs),
        patch("sys.stdout", new=StringIO()) as fake_out,
    ):
        from chronicler.core.wizard import ApiKeyStep

        step = ApiKeyStep()
        step.run(settings)

        assert settings.api_key is not None
        assert len(settings.api_key) == 43
        assert "Generated API key:" in fake_out.getvalue()


def test_remote_server_step_reprompts_on_empty_api_key():
    """
    RemoteServerStep connects to an existing server, so the key must match one the server
    operator already configured - generating a random one on blank input (the old behavior)
    silently guaranteed every subsequent request would 403.
    """
    settings = Settings()
    inputs = ["http://localhost:8000", "", "the-real-server-key"]

    with (
        patch("builtins.input", side_effect=inputs),
        patch("sys.stdout", new=StringIO()) as fake_out,
    ):
        from chronicler.core.wizard import RemoteServerStep

        step = RemoteServerStep()
        step.run(settings)

        assert settings.server_url == "http://localhost:8000"
        assert settings.api_key == "the-real-server-key"
        assert "cannot be generated here" in fake_out.getvalue()


@patch("chronicler.core.wizard.WorkspaceStep.run")
@patch("chronicler.core.wizard.ApiKeyStep.run")
def test_wizard_run_server_mode(mock_api, mock_ws, tmp_path):
    with (
        patch("chronicler.core.config.user_config_dir", return_value=str(tmp_path)),
        patch("chronicler.core.wizard.LanguageStep.run"),
    ):
        settings = Settings(workspace_path=None)
        wizard = ConfigWizard(settings=settings)
        wizard.run(mode="server")

    mock_ws.assert_called_once()
    mock_api.assert_called_once()
    assert settings.mode == "server"


@patch("chronicler.core.wizard.RemoteServerStep.run")
def test_wizard_run_webclient_mode(mock_remote, tmp_path):
    with (
        patch("chronicler.core.config.user_config_dir", return_value=str(tmp_path)),
        patch("chronicler.core.wizard.LanguageStep.run"),
    ):
        settings = Settings(server_url=None)
        wizard = ConfigWizard(settings=settings)
        wizard.run(mode="client:web")

    mock_remote.assert_called_once()
    assert settings.mode == "client:web"


@patch("chronicler.core.wizard.ConfigWizard._show_main_choice")
def test_wizard_run_desktop_mode_missing(mock_choice, tmp_path):
    with patch("chronicler.core.config.user_config_dir", return_value=str(tmp_path)):
        settings = Settings(workspace_path=None, server_url=None)
        wizard = ConfigWizard(settings=settings)
        wizard.run(mode="client:desktop")

    mock_choice.assert_called_once()


def test_wizard_skips_satisfied_steps(tmp_path):
    with patch("chronicler.core.config.user_config_dir", return_value=str(tmp_path)):
        settings = Settings(api_key="existing-key", workspace_path=None)
        wizard = ConfigWizard(settings=settings)

        with (
            patch("chronicler.core.wizard.WorkspaceStep.run") as mock_ws,
            patch("chronicler.core.wizard.ApiKeyStep.run") as mock_api,
            patch("chronicler.core.wizard.LanguageStep.run"),
        ):
            wizard.run(mode="server")

            mock_ws.assert_called_once()
            mock_api.assert_not_called()


def test_wizard_desktop_choice_skips_satisfied_steps(tmp_path):
    with patch("chronicler.core.config.user_config_dir", return_value=str(tmp_path)):
        settings = Settings(api_key="existing-key", workspace_path=None, server_url=None)
        wizard = ConfigWizard(settings=settings)

        with (
            patch("builtins.input", return_value="1"),
            patch("chronicler.core.wizard.WorkspaceStep.run") as mock_ws,
            patch("chronicler.core.wizard.ApiKeyStep.run") as mock_api,
        ):
            wizard.run(mode="client:desktop")

            mock_ws.assert_called_once()
            mock_api.assert_not_called()
