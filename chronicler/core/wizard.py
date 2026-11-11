"""
Setup helpers shared by the desktop wizard, and the server's one-step setup.

The desktop collects its configuration on screen (`desktop.views.wizard`). The server has no
screen, and often no terminal either - under Docker or systemd - so it is configured with
flags or environment variables, and asks only when a terminal is attached.
"""

import secrets
import sys
from collections.abc import Callable
from pathlib import Path

from chronicler.core.config import Mode, Settings

LANGUAGE_NAMES = {"en": "English", "nl": "Nederlands", "de": "Deutsch"}


class SetupError(RuntimeError):
    """The server cannot be set up with what it was given; the message says what to pass."""


def supported_languages() -> list[str]:
    """The locales Chronicler ships, offered for both the interface and transcription."""
    return list(LANGUAGE_NAMES)


def default_workspace_path() -> Path:
    """A sensible per-OS home for the workspace, preferring the user's Documents folder."""
    home = Path.home()
    documents = home / "Documents"
    base = documents if documents.is_dir() else home
    return (base / "Chronicler").expanduser()


def configure_server(
    settings: Settings,
    workspace: str | None = None,
    api_key: str | None = None,
    interactive: bool | None = None,
    ask: Callable[[str], str] = input,
    say: Callable[[str], None] = print,
) -> bool:
    """
    Fills in what `chronicler server` needs - a workspace and an API key - and saves it.

    `workspace` and `api_key` (the command-line flags) win over what is already configured.
    A missing workspace is asked for when `interactive` (default: stdin is a terminal), and
    otherwise raises SetupError naming the flag. A missing key is generated and printed
    once. Returns whether anything was saved.
    """
    if interactive is None:
        interactive = sys.stdin is not None and sys.stdin.isatty()

    changed = False
    if workspace:
        settings.workspace_path = Path(workspace).expanduser().resolve()
        changed = True
    if settings.workspace_path is None:
        if not interactive:
            raise SetupError(
                "No workspace is configured. Pass --workspace PATH, or set "
                "CHRONICLER_WORKSPACE_PATH."
            )
        default = default_workspace_path()
        typed = ask(f"Workspace folder [{default}]: ").strip()
        settings.workspace_path = Path(typed).expanduser().resolve() if typed else default
        changed = True

    path = settings.workspace_path
    # A folder that does not exist yet is created at startup; one that exists has to take a
    # file now, or startup would refuse it.
    if path.exists() and not settings.is_workspace_valid():
        raise SetupError(f"Chronicler cannot write to {path}. Choose a different --workspace.")

    if api_key:
        settings.api_key = api_key
        changed = True
    if not settings.api_key:
        settings.api_key = secrets.token_urlsafe(32)
        say(f"Generated API key (shown once, also saved in the configuration): {settings.api_key}")
        changed = True

    if settings.mode is not Mode.SERVER:
        settings.mode = Mode.SERVER
        changed = True

    if changed:
        say(f"Configuration saved to {settings.save()}")
    return changed
