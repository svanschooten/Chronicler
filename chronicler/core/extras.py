"""The optional extras, what each one needs, and installing one on demand."""

import importlib
import logging
import os
import subprocess
import sys
import sysconfig
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

INSTALL_TIMEOUT_SECONDS = 900


@dataclass(frozen=True)
class Extra:
    """One optional dependency group, as declared in pyproject.toml."""

    name: str
    module: str
    requirement: str
    purpose: str
    download_mb: int
    system_packages: tuple[str, ...] = ()
    note: str = ""
    apt_hint: str = field(default="", repr=False)

    @property
    def pip_extra(self) -> str:
        return f"chronicler[{self.name}]"


EXTRAS: dict[str, Extra] = {
    "transcription": Extra(
        name="transcription",
        module="faster_whisper",
        requirement="faster-whisper>=1.1,<2",
        purpose="Transcribing audio with Whisper",
        download_mb=120,
        note="The Whisper model itself is downloaded separately the first time it runs.",
    ),
    "normalization": Extra(
        name="normalization",
        module="av",
        requirement="av>=12,<19",
        purpose="Normalizing the loudness of an audio source",
        download_mb=35,
    ),
    "llm": Extra(
        name="llm",
        module="llama_cpp",
        requirement="llama-cpp-python>=0.3,<1",
        purpose="Running a local GGUF language model for summaries",
        download_mb=30,
        note="Only needed for local models; a remote OpenAI-compatible gateway needs nothing.",
    ),
    "recording": Extra(
        name="recording",
        module="sounddevice",
        requirement="sounddevice>=0.4,<1",
        purpose="Recording audio from a microphone",
        download_mb=1,
        system_packages=("libportaudio2",),
        note="sounddevice is a binding, not a bundle: it needs PortAudio from the system.",
        apt_hint="sudo apt install libportaudio2",
    ),
}


@dataclass(frozen=True)
class InstallResult:
    ok: bool
    output: str


def get_extra(name: str) -> Extra:
    try:
        return EXTRAS[name]
    except KeyError as error:
        raise KeyError(f"Unknown extra {name!r}") from error


def is_available(name: str) -> bool:
    """
    Whether `name`'s module can actually be imported right now.

    A real import, not a find_spec check: a binding whose system library is absent
    imports and then raises. See docs/optional-extras.md.
    """
    extra = get_extra(name)
    try:
        importlib.import_module(extra.module)
    except Exception:
        logger.debug(f"Extra {name!r} is unavailable", exc_info=True)
        return False
    return True


def download_estimate(name: str) -> str:
    return f"~{get_extra(name).download_mb} MB"


def missing_message(name: str, error: BaseException | None = None) -> str:
    """What to tell the user when `name` is needed and not there."""
    extra = get_extra(name)

    if extra.system_packages and error is not None and not isinstance(error, ImportError):
        return (
            f"{extra.purpose} needs the system library "
            f"{', '.join(extra.system_packages)}, which is not installed "
            f"({extra.apt_hint})."
        )

    if is_frozen():
        # Naming a pip command here would be a lie: there is no environment to install
        # into. A release bundles the extras, so this only happens on a build that left
        # one out deliberately.
        return f"{extra.purpose} is not included in this build of Chronicler."

    message = f"{extra.purpose} requires the '{extra.name}' extra ({extra.pip_extra})."
    if extra.system_packages:
        message += f" On Linux it also needs {', '.join(extra.system_packages)} ({extra.apt_hint})."
    return message


def is_frozen() -> bool:
    """Whether this is a PyInstaller build rather than a Python installation."""
    return bool(getattr(sys, "frozen", False))


def can_install() -> bool:
    """
    Whether this interpreter's environment can be written to by pip.

    Never in a packaged build. There is no pip in the bundle, `sys.prefix` and
    `sys.base_prefix` are both the extraction directory, and `sys.executable` is
    Chronicler itself - so `sys.executable -m pip install` would relaunch the app with
    nonsense arguments rather than install anything. A release ships the extras instead;
    see docs/optional-extras.md.
    """
    if is_frozen():
        return False
    if sys.prefix != sys.base_prefix:
        return True
    purelib = sysconfig.get_paths().get("purelib")
    return purelib is not None and os.access(purelib, os.W_OK)


def is_usable(name: str) -> bool:
    """
    Whether the feature behind `name` can run - now, or after an install the user can
    actually perform.

    This is what a button asks before greying itself out. A source checkout missing an
    extra is a prompt away from having it; a packaged build missing one is not.
    """
    return is_available(name) or can_install()


def install_command(name: str) -> list[str]:
    """
    The requirement is installed directly rather than as `chronicler[<name>]`: Chronicler
    is not published, so resolving itself from an index would fail. See
    docs/optional-extras.md.
    """
    return [sys.executable, "-m", "pip", "install", get_extra(name).requirement]


def install(name: str) -> InstallResult:
    """Installs one extra, reporting rather than raising when it does not work."""
    extra = get_extra(name)
    command = install_command(name)
    logger.info(f"Installing the {extra.name} extra: {' '.join(command)}")

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=INSTALL_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return InstallResult(ok=False, output=str(error))

    output = _tail(completed.stdout, completed.stderr)
    if completed.returncode != 0:
        logger.warning(f"Installing {extra.name} failed: {output}")
        return InstallResult(ok=False, output=output)

    importlib.invalidate_caches()
    if not is_available(name):
        return InstallResult(ok=False, output=missing_message(name, OSError(output)))

    logger.info(f"The {extra.name} extra is now available")
    return InstallResult(ok=True, output=output)


def _tail(stdout: str | None, stderr: str | None, lines: int = 8) -> str:
    """The last few lines of pip's own output, which is where its reason lives."""
    combined = "\n".join(part.strip() for part in (stdout, stderr) if part and part.strip())
    return "\n".join(combined.splitlines()[-lines:])
