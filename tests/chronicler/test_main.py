import logging
from unittest.mock import MagicMock, patch

from chronicler.__main__ import main
from chronicler.core.config import Settings


def test_main_default_mode():
    with (
        patch("sys.argv", ["chronicler"]),
        patch("chronicler.core.config.is_config_initialized", return_value=True),
        patch("chronicler.core.config.get_settings") as mock_get_settings,
        patch("chronicler.desktop.main.run_desktop") as mock_run_desktop,
    ):
        mock_settings = MagicMock()
        mock_settings.validate_for_mode.return_value = True
        mock_get_settings.return_value = mock_settings

        main()

        mock_run_desktop.assert_called_once()
        mock_settings.validate_for_mode.assert_called_with("client:desktop")


def test_main_server_mode():
    with (
        patch("sys.argv", ["chronicler", "server"]),
        patch("chronicler.core.config.is_config_initialized", return_value=True),
        patch("chronicler.core.config.get_settings") as mock_get_settings,
        patch("chronicler.server.main.run_server") as mock_run_server,
    ):
        mock_settings = MagicMock()
        mock_settings.validate_for_mode.return_value = True
        mock_get_settings.return_value = mock_settings

        main()

        mock_run_server.assert_called_once()
        mock_settings.validate_for_mode.assert_called_with("server")


def test_main_web_mode():
    with (
        patch("sys.argv", ["chronicler", "client:web"]),
        patch("chronicler.core.config.is_config_initialized", return_value=True),
        patch("chronicler.core.config.get_settings") as mock_get_settings,
        patch("chronicler.webclient.main.run_server") as mock_run_web_server,
    ):
        mock_settings = MagicMock()
        mock_settings.validate_for_mode.return_value = True
        mock_get_settings.return_value = mock_settings

        main()

        mock_run_web_server.assert_called_once()
        mock_settings.validate_for_mode.assert_called_with("client:web")


def test_main_verbose_logging():
    with (
        patch("sys.argv", ["chronicler", "--verbose"]),
        patch("logging.basicConfig") as mock_logging_config,
        patch("chronicler.core.config.is_config_initialized", return_value=True),
        patch("chronicler.core.config.get_settings") as mock_get_settings,
        patch("chronicler.desktop.main.run_desktop"),
    ):
        mock_settings = MagicMock()
        mock_settings.validate_for_mode.return_value = True
        mock_get_settings.return_value = mock_settings

        main()

        mock_settings.validate_for_mode.assert_called_with("client:desktop")

        _, kwargs = mock_logging_config.call_args
        assert kwargs["level"] == logging.DEBUG


def test_main_web_mode_alias():
    with (
        patch("sys.argv", ["chronicler", "web"]),
        patch("chronicler.core.config.is_config_initialized", return_value=True),
        patch("chronicler.core.config.get_settings") as mock_get_settings,
        patch("chronicler.webclient.main.run_server") as mock_run_web_server,
    ):
        mock_settings = MagicMock()
        mock_settings.validate_for_mode.return_value = True
        mock_get_settings.return_value = mock_settings

        main()

        mock_run_web_server.assert_called_once()
        mock_settings.validate_for_mode.assert_called_with("client:web")


def test_main_desktop_mode_alias():
    with (
        patch("sys.argv", ["chronicler", "desktop"]),
        patch("chronicler.core.config.is_config_initialized", return_value=True),
        patch("chronicler.core.config.get_settings") as mock_get_settings,
        patch("chronicler.desktop.main.run_desktop") as mock_run_desktop,
    ):
        mock_settings = MagicMock()
        mock_settings.validate_for_mode.return_value = True
        mock_get_settings.return_value = mock_settings

        main()

        mock_run_desktop.assert_called_once()
        mock_settings.validate_for_mode.assert_called_with("client:desktop")


@patch("chronicler.core.wizard.run_wizard")
@patch("chronicler.core.config.is_config_initialized", return_value=True)
@patch("chronicler.core.config.get_settings")
def test_main_checks_validity(mock_get_settings, mock_is_init, mock_run_wizard):
    import sys

    mock_settings = MagicMock(spec=Settings)
    mock_settings.validate_for_mode.return_value = False
    mock_get_settings.return_value = mock_settings

    with (
        patch.object(sys, "argv", ["chronicler", "server"]),
        patch("chronicler.__main__.server_main"),
    ):
        main()

    mock_settings.validate_for_mode.assert_called_with("server")
    mock_run_wizard.assert_called_with(mode="server")


@patch("chronicler.core.wizard.run_wizard")
@patch("chronicler.core.config.is_config_initialized", return_value=True)
@patch("chronicler.core.config.get_settings")
def test_main_skips_wizard_if_valid(mock_get_settings, mock_is_init, mock_run_wizard):
    import sys

    mock_settings = MagicMock(spec=Settings)
    mock_settings.validate_for_mode.return_value = True
    mock_get_settings.return_value = mock_settings

    with (
        patch.object(sys, "argv", ["chronicler", "server"]),
        patch("chronicler.__main__.server_main"),
    ):
        main()

    mock_settings.validate_for_mode.assert_called_with("server")
    mock_run_wizard.assert_not_called()
