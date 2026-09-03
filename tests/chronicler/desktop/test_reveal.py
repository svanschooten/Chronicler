from unittest.mock import MagicMock, patch

import pytest

from chronicler.desktop.reveal import (
    RevealError,
    describe_desktop_integration_error,
    file_manager_command,
    open_in_file_manager,
)


class TestFileManagerCommand:
    def test_macos_uses_open(self, tmp_path):
        assert file_manager_command(tmp_path, "darwin", is_wsl=False) == ["open", str(tmp_path)]

    def test_windows_uses_explorer(self, tmp_path):
        assert file_manager_command(tmp_path, "win32", is_wsl=False) == [
            "explorer",
            str(tmp_path),
        ]

    def test_linux_uses_xdg_open(self, tmp_path):
        assert file_manager_command(tmp_path, "linux", is_wsl=False) == [
            "xdg-open",
            str(tmp_path),
        ]

    def test_wsl_shells_out_to_windows_explorer(self, tmp_path):
        command = file_manager_command(tmp_path, "linux", is_wsl=True)

        assert command[0] == "explorer.exe"
        assert command[1] == str(tmp_path)


class TestOpenInFileManager:
    def test_runs_the_platform_command(self, tmp_path):
        with (
            patch("chronicler.desktop.reveal._is_wsl", return_value=False),
            patch("chronicler.desktop.reveal.subprocess.Popen") as popen,
        ):
            open_in_file_manager(tmp_path)

        popen.assert_called_once()
        assert str(tmp_path) in popen.call_args.args[0]

    def test_a_missing_directory_is_refused(self, tmp_path):
        with pytest.raises(RevealError, match="does not exist"):
            open_in_file_manager(tmp_path / "nope")

    def test_a_launch_failure_is_reported(self, tmp_path):
        with (
            patch("chronicler.desktop.reveal._is_wsl", return_value=False),
            patch(
                "chronicler.desktop.reveal.subprocess.Popen",
                side_effect=FileNotFoundError("no xdg"),
            ),
        ):
            with pytest.raises(RevealError):
                open_in_file_manager(tmp_path)

    def test_wsl_translates_the_path_when_wslpath_succeeds(self, tmp_path):
        completed = MagicMock(returncode=0, stdout="C:\\\\Users\\\\me\\\\ws\n")
        with (
            patch("chronicler.desktop.reveal._is_wsl", return_value=True),
            patch("chronicler.desktop.reveal.subprocess.run", return_value=completed),
            patch("chronicler.desktop.reveal.subprocess.Popen") as popen,
        ):
            open_in_file_manager(tmp_path)

        assert popen.call_args.args[0] == ["explorer.exe", "C:\\\\Users\\\\me\\\\ws"]

    def test_wsl_falls_back_to_the_raw_path_when_wslpath_fails(self, tmp_path):
        with (
            patch("chronicler.desktop.reveal._is_wsl", return_value=True),
            patch("chronicler.desktop.reveal.subprocess.run", side_effect=OSError("nope")),
            patch("chronicler.desktop.reveal.subprocess.Popen") as popen,
        ):
            open_in_file_manager(tmp_path)

        assert popen.call_args.args[0] == ["explorer.exe", str(tmp_path)]


class TestDescribeDesktopIntegrationError:
    def test_a_missing_session_bus_names_the_fix(self):
        error = Exception(
            "SocketException: Connection failed (OS Error: No such file or directory, "
            "errno = 2), address = /run/user/1000/bus, port = 0"
        )

        message = describe_desktop_integration_error(error)

        assert "loginctl enable-linger" in message
        assert "/run/user/1000/bus" not in message

    def test_a_missing_portal_is_recognised(self):
        message = describe_desktop_integration_error(
            Exception("org.freedesktop.portal.Desktop was not provided by any .service files")
        )

        assert "portal" in message.lower()

    def test_a_dbus_failure_is_recognised(self):
        message = describe_desktop_integration_error(Exception("Failed to connect to DBus"))

        assert "loginctl enable-linger" in message

    def test_an_unrelated_error_is_passed_through(self):
        message = describe_desktop_integration_error(Exception("disk on fire"))

        assert "disk on fire" in message
        assert "loginctl" not in message

    def test_the_message_is_one_line_for_a_snackbar(self):
        message = describe_desktop_integration_error(Exception("address = /run/user/1000/bus"))

        assert "\n" not in message
