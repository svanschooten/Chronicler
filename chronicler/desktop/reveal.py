"""Opening a directory in the operating system's own file manager."""

import logging
import os
import platform
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


class RevealError(RuntimeError):
    """The directory could not be shown in a file manager."""


def _is_wsl() -> bool:
    return "microsoft" in platform.uname().release.lower()


def _windows_path(path: Path) -> str:
    """The Windows spelling of a WSL path, falling back to the raw path."""
    try:
        result = subprocess.run(
            ["wslpath", "-w", str(path)], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        logger.debug("wslpath unavailable; using the raw path", exc_info=True)
    return str(path)


def file_manager_command(path: Path, platform_name: str, is_wsl: bool) -> list[str]:
    if is_wsl:
        return ["explorer.exe", str(path)]
    if platform_name == "darwin":
        return ["open", str(path)]
    if platform_name.startswith("win"):
        return ["explorer", str(path)]
    return ["xdg-open", str(path)]


def open_in_file_manager(path: Path) -> None:
    """Shows `path` in the native file manager, raising RevealError if it cannot."""
    if not path.exists():
        raise RevealError(f"{path} does not exist")

    is_wsl = _is_wsl()
    target = Path(_windows_path(path)) if is_wsl else path
    command = file_manager_command(target, sys.platform, is_wsl)

    try:
        subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=os.name != "nt",
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RevealError(f"Could not open {path}: {error}") from error


_SESSION_BUS_HINTS = ("/run/user/", "dbus", "d-bus", "session bus")
_PORTAL_HINTS = ("org.freedesktop.portal", "xdg-desktop-portal")


def describe_desktop_integration_error(error: BaseException) -> str:
    """
    A message a user can act on when a native dialog cannot reach the desktop.

    File dialogs go through the XDG desktop portal over the session D-Bus. On WSL, and on
    any login that never registers a systemd session, `$XDG_RUNTIME_DIR` is exported but
    never created, so the socket behind it does not exist and the raw error is an errno
    against a path that means nothing to the person reading it.
    """
    text = str(error)
    lowered = text.lower()

    if any(hint in lowered for hint in _SESSION_BUS_HINTS):
        return (
            "Could not open the system file dialog: no desktop session bus is running. "
            "On WSL or a headless login, run 'sudo loginctl enable-linger $USER' and "
            "restart the session."
        )
    if any(hint in lowered for hint in _PORTAL_HINTS):
        return (
            "Could not open the system file dialog: the XDG desktop portal is not "
            "available. Install xdg-desktop-portal and a backend such as "
            "xdg-desktop-portal-gtk."
        )
    return text
