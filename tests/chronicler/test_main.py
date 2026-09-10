import logging
import sys
import types
from unittest.mock import MagicMock, patch

from chronicler.__main__ import attach_windows_console, main
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


@patch("chronicler.core.wizard.run_wizard")
@patch("chronicler.core.config.is_config_initialized", return_value=False)
def test_desktop_mode_never_reaches_for_the_console_wizard(mock_is_init, mock_run_wizard):
    """
    The packaged desktop build is windowless and has no stdin, so setup happens on screen
    (chronicler.desktop.views.wizard). Even with nothing configured at all, `main()` must
    not call the console wizard - it would raise on `input()` with no console attached.
    """
    with (
        patch.object(sys, "argv", ["chronicler", "desktop"]),
        patch("chronicler.desktop.main.run_desktop") as mock_run_desktop,
    ):
        main()

    mock_run_wizard.assert_not_called()
    mock_run_desktop.assert_called_once()


@patch("chronicler.core.wizard.run_wizard")
@patch("chronicler.core.config.is_config_initialized", return_value=False)
def test_server_mode_still_uses_the_console_wizard(mock_is_init, mock_run_wizard):
    """Server is started from a terminal, which is exactly where the console wizard works."""
    with (
        patch.object(sys, "argv", ["chronicler", "server"]),
        patch("chronicler.__main__.server_main"),
    ):
        main()

    mock_run_wizard.assert_called_once_with(mode="server")


class TestWindowsConsole:
    """
    The windowless build gets no console of its own, not even the one it was launched from,
    which would leave `--help` and `chronicler server` with nowhere to write or read.
    """

    @staticmethod
    def _fake_ctypes(attach_result: int) -> tuple[types.SimpleNamespace, MagicMock]:
        kernel32 = MagicMock()
        kernel32.AttachConsole.return_value = attach_result
        return types.SimpleNamespace(windll=types.SimpleNamespace(kernel32=kernel32)), kernel32

    def test_it_is_a_no_op_off_windows(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")

        assert attach_windows_console() is False

    @staticmethod
    def _console_only_open(opened: list[str]):
        """
        Stands in for the console devices without touching the filesystem.

        Off Windows `CONOUT$` is not a device but an ordinary relative path, so letting the
        real `open` see it in write mode creates a junk file in the working directory.
        Everything else is delegated so pytest's own file access still works.
        """
        real_open = open

        def fake_open(file, *args, **kwargs):
            if file in ("CONIN$", "CONOUT$"):
                opened.append(file)
                return MagicMock()
            return real_open(file, *args, **kwargs)

        return fake_open

    def test_it_borrows_the_console_of_the_terminal_that_started_it(self, monkeypatch):
        fake_ctypes, kernel32 = self._fake_ctypes(attach_result=1)
        opened: list[str] = []
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setitem(sys.modules, "ctypes", fake_ctypes)
        monkeypatch.setattr("builtins.open", self._console_only_open(opened))
        for stream in ("stdin", "stdout", "stderr"):
            monkeypatch.setattr(sys, stream, None)

        assert attach_windows_console() is True
        kernel32.AttachConsole.assert_called_once_with(-1)
        assert opened == ["CONIN$", "CONOUT$", "CONOUT$"]
        assert all(getattr(sys, stream) is not None for stream in ("stdin", "stdout", "stderr")), (
            "all three streams have to be reopened, or half the output still goes nowhere"
        )

    def test_a_stream_that_will_not_reopen_does_not_sink_the_rest(self, monkeypatch):
        """One unavailable device should not cost the process the console it just attached."""
        fake_ctypes, _ = self._fake_ctypes(attach_result=1)
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setitem(sys.modules, "ctypes", fake_ctypes)
        monkeypatch.setattr("builtins.open", MagicMock(side_effect=OSError("no such device")))
        for stream in ("stdin", "stdout", "stderr"):
            monkeypatch.setattr(sys, stream, MagicMock())

        assert attach_windows_console() is True

    def test_it_gives_up_when_there_is_no_console_to_borrow(self, monkeypatch):
        """A double-clicked app has no parent console; it stays a pure GUI app."""
        fake_ctypes, kernel32 = self._fake_ctypes(attach_result=0)
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setitem(sys.modules, "ctypes", fake_ctypes)
        stdout = MagicMock()
        monkeypatch.setattr(sys, "stdout", stdout)

        assert attach_windows_console() is False
        assert sys.stdout is stdout, "it must not touch the streams it could not replace"
