"""The optional extras, what each one needs, and installing one on demand."""

import importlib
import logging
import os
import subprocess
import sys
import sysconfig
from dataclasses import dataclass, field
from pathlib import Path

from chronicler.i18n import t

logger = logging.getLogger(__name__)

INSTALL_TIMEOUT_SECONDS = 900
COMPONENT_LOCKS = Path("share") / "chronicler" / "locks"


@dataclass(frozen=True)
class Extra:
    """
    One optional dependency group, as declared in pyproject.toml. `modules` are what its
    guard imports, one per package the feature imports directly; `requirements` are the
    group's entries exactly as pyproject.toml lists them.
    """

    name: str
    modules: tuple[str, ...]
    requirements: tuple[str, ...]
    download_mb: int
    system_packages: tuple[str, ...] = ()
    has_note: bool = False
    apt_hint: str = field(default="", repr=False)

    @property
    def purpose(self) -> str:
        """What the extra is for, in the interface language - `extras.purposes.<name>`."""
        return t(f"extras.purposes.{self.name}")

    @property
    def note(self) -> str:
        """An aside shown with the install prompt, or "" - `extras.notes.<name>`."""
        return t(f"extras.notes.{self.name}") if self.has_note else ""

    @property
    def pip_extra(self) -> str:
        return f"chronicler[{self.name}]"

    @property
    def requirements_text(self) -> str:
        """The requirements on one line, for messages."""
        return ", ".join(self.requirements)


EXTRAS: dict[str, Extra] = {
    "transcription": Extra(
        name="transcription",
        modules=("faster_whisper",),
        requirements=("faster-whisper>=1.1,<2",),
        download_mb=120,
        has_note=True,
    ),
    "normalization": Extra(
        name="normalization",
        modules=("av", "numpy"),
        requirements=("av>=12,<20", "numpy>=1.26,<3"),
        download_mb=50,
    ),
    "llm": Extra(
        name="llm",
        modules=("llama_cpp",),
        requirements=("llama-cpp-python>=0.3,<1",),
        download_mb=30,
        has_note=True,
    ),
    "recording": Extra(
        name="recording",
        modules=("sounddevice",),
        requirements=("sounddevice>=0.4,<1",),
        download_mb=1,
        system_packages=("libportaudio2",),
        has_note=True,
        apt_hint="sudo apt install libportaudio2",
    ),
    "server": Extra(
        name="server",
        modules=("fastapi", "uvicorn", "python_multipart"),
        requirements=(
            "fastapi>=0.141.1,<1",
            "uvicorn[standard]>=0.30,<1",
            "python-multipart>=0.0.13",
        ),
        download_mb=10,
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
    Whether all of `name`'s modules can actually be imported right now.

    A real import, not a find_spec check: a binding whose system library is absent
    imports and then raises. See docs/optional-extras.md.
    """
    extra = get_extra(name)
    try:
        for module in extra.modules:
            importlib.import_module(module)
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

    if is_embedded_runtime():
        if not is_component(name):
            return f"{extra.purpose} is not included in this build of Chronicler."
        return (
            f"{extra.purpose} is a downloadable component. Install it by running the "
            f"Chronicler executable with: components install {extra.name}"
        )

    message = f"{extra.purpose} requires the '{extra.name}' extra ({extra.pip_extra})."
    if extra.system_packages:
        message += f" On Linux it also needs {', '.join(extra.system_packages)} ({extra.apt_hint})."
    return message


def is_frozen() -> bool:
    """Whether this is a PyInstaller build rather than a Python installation."""
    return bool(getattr(sys, "frozen", False))


def is_embedded_runtime() -> bool:
    """
    Whether this is the embedded-runtime build, recognised by the component locks it ships.
    See docs/runtime-build.md.
    """
    return (Path(sys.prefix) / COMPONENT_LOCKS).is_dir()


def is_component(name: str) -> bool:
    """Whether the embedded runtime can download `name` as a component."""
    return (Path(sys.prefix) / COMPONENT_LOCKS / f"component-{name}.lock").is_file()


def can_install() -> bool:
    """
    Whether this interpreter's environment can be written to by pip.

    Never in a packaged build. There is no pip in the bundle, `sys.prefix` and
    `sys.base_prefix` are both the extraction directory, and `sys.executable` is
    Chronicler itself - so `sys.executable -m pip install` would relaunch the app with
    nonsense arguments rather than install anything. A release ships the extras instead;
    see docs/optional-extras.md.

    Not through pip in the embedded runtime either: an unpinned package installed into it
    is gone after the next update. Components install from the locks it ships instead.
    """
    if is_frozen() or is_embedded_runtime():
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
    return [sys.executable, "-m", "pip", "install", *get_extra(name).requirements]


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
