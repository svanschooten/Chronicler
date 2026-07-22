import logging
from unittest.mock import MagicMock, patch

from chronicler.__main__ import main


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
    # Test both 'server' and 'client:web' (existing) and new 'web' alias if I add it
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
    # Testing 'client:web' (current)
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

        # Check if logging level was set to DEBUG
        _, kwargs = mock_logging_config.call_args
        assert kwargs["level"] == logging.DEBUG


def test_main_web_mode_alias():
    # Testing 'web' alias
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
    # Testing 'desktop' alias
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
