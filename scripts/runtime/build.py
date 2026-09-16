#!/usr/bin/env python
"""
Builds the embedded-runtime Chronicler executable for this platform.

A standalone CPython gets the base dependencies from the hash-pinned lock, the Chronicler
wheel, the Flet client and the component locks; it is trimmed, archived with zstd and
embedded into a PyApp launcher. Needs uv and cargo on PATH, and the `zstandard` package:

    uv run --no-project --with zstandard python scripts/runtime/build.py --variant console
"""

import argparse
import compileall
import glob
import hashlib
import os
import platform as host_platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.runtime.locks import LOCKS_DIR, uv  # noqa: E402
from scripts.runtime.pins import (  # noqa: E402
    FLET_CLIENT_VERSION,
    FLET_CLIENTS,
    PLATFORMS,
    PYAPP_SOURCE,
    PYTHON_RUNTIMES,
    PYTHON_VERSION,
    Artifact,
)

LAUNCHER_MODULE = "chronicler_launcher"
WINDOWS_GUI_ATTRIBUTE = '#![windows_subsystem = "windows"]'


def log(message: str) -> None:
    print(f"[runtime] {message}", flush=True)


def host() -> str:
    system = host_platform.system().lower()
    if system not in PLATFORMS:
        raise SystemExit(f"Unsupported build platform: {system}")
    return system


def chronicler_version() -> str:
    text = (REPO_ROOT / "chronicler" / "__init__.py").read_text()
    match = re.search(r'^__version__ = "([^"]+)"', text, re.MULTILINE)
    if not match:
        raise SystemExit("No __version__ in chronicler/__init__.py")
    return match.group(1)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(artifact: Artifact, cache: Path) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / artifact.filename
    if not target.exists() or sha256_of(target) != artifact.sha256:
        log(f"downloading {artifact.url}")
        partial = target.with_suffix(target.suffix + ".part")
        with urllib.request.urlopen(artifact.url, timeout=120) as response:
            with partial.open("wb") as handle:
                shutil.copyfileobj(response, handle)
        actual = sha256_of(partial)
        if actual != artifact.sha256:
            partial.unlink()
            raise SystemExit(f"Checksum mismatch for {artifact.url}: {actual}")
        partial.replace(target)
    return target


def extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(destination)
    else:
        with tarfile.open(archive) as bundle:
            bundle.extractall(destination, filter="data")


def run(*command: str | Path, env: dict[str, str] | None = None, cwd: Path | None = None) -> None:
    subprocess.run([str(part) for part in command], check=True, env=env, cwd=cwd)


def pip_install(python: Path, *arguments: str | Path) -> None:
    run(
        python,
        "-m",
        "pip",
        "install",
        "--isolated",
        "--disable-pip-version-check",
        "--no-warn-script-location",
        "--no-deps",
        *arguments,
    )


def build_wheel(work: Path) -> Path:
    out = work / "wheel"
    shutil.rmtree(out, ignore_errors=True)
    run(*uv(), "build", "--wheel", "--out-dir", out, REPO_ROOT)
    (wheel,) = out.glob("chronicler-*.whl")
    return wheel


def install_flet_client(platform: str, python: Path, root: Path, cache: Path) -> None:
    installed = subprocess.run(
        [str(python), "-c", "import flet_desktop.version as v; print(v.version)"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if installed != FLET_CLIENT_VERSION:
        raise SystemExit(
            f"flet-desktop {installed} is locked but the pinned client is {FLET_CLIENT_VERSION}"
        )

    executable = "flet.exe" if platform == "windows" else "flet"
    with tempfile.TemporaryDirectory() as scratch:
        extract(fetch(FLET_CLIENTS[platform], cache), Path(scratch))
        candidates = [path for path in Path(scratch).rglob(executable) if path.is_file()]
        if not candidates:
            raise SystemExit(f"No {executable} in {FLET_CLIENTS[platform].filename}")
        found = min(candidates, key=lambda path: len(path.parts)).parent
        target = root / "python" / "share" / "flet-client"
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(found, target, symlinks=True)


def trim(root: Path, patterns: tuple[str, ...]) -> None:
    for pattern in patterns:
        for match in glob.glob(str(root / pattern)):
            path = Path(match)
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()


def archive_runtime(root: Path, work: Path) -> Path:
    import zstandard  # type: ignore[import-not-found]

    staging = work / "runtime.tar.zst"
    compressor = zstandard.ZstdCompressor(level=19, threads=-1)
    with staging.open("wb") as handle, compressor.stream_writer(handle) as stream:
        with tarfile.open(fileobj=stream, mode="w|") as bundle:
            bundle.add(root / "python", arcname="python")

    # A content-addressed name makes cargo re-embed the archive whenever it changes.
    archive = work / f"runtime-{sha256_of(staging)[:12]}.tar.zst"
    for stale in work.glob("runtime-*.tar.zst"):
        stale.unlink()
    staging.replace(archive)
    return archive


def use_windows_gui_subsystem(main: Path) -> None:
    """
    PyApp's launcher is always a console executable, so double-clicking even its GUI
    variant opens a console window next to the app. See docs/runtime-build.md.
    """
    text = main.read_text()
    if WINDOWS_GUI_ATTRIBUTE not in text:
        main.write_text(f"{WINDOWS_GUI_ATTRIBUTE}\n{text}")


def build_launcher(
    platform: str, archive: Path, variant: str, version: str, work: Path, cache: Path
) -> Path:
    cargo = shutil.which("cargo")
    if cargo is None:
        raise SystemExit("cargo is required to build the PyApp launcher")

    source_root = work / "pyapp-src"
    shutil.rmtree(source_root, ignore_errors=True)
    extract(fetch(PYAPP_SOURCE, cache), source_root)
    (source,) = [path.parent for path in source_root.rglob("Cargo.toml")]
    if variant == "gui" and platform == "windows":
        use_windows_gui_subsystem(source / "src" / "main.rs")

    spec = PLATFORMS[platform]
    env = {
        **os.environ,
        "CARGO_TARGET_DIR": str(work / "pyapp-target"),
        "PYAPP_PROJECT_NAME": "chronicler",
        "PYAPP_PROJECT_VERSION": version,
        "PYAPP_PYTHON_VERSION": PYTHON_VERSION,
        "PYAPP_DISTRIBUTION_EMBED": "1",
        "PYAPP_DISTRIBUTION_PATH": str(archive),
        "PYAPP_DISTRIBUTION_FORMAT": "tar|zstd",
        "PYAPP_DISTRIBUTION_PYTHON_PATH": spec.python_path,
        "PYAPP_DISTRIBUTION_SITE_PACKAGES_PATH": spec.site_packages,
        "PYAPP_DISTRIBUTION_PIP_AVAILABLE": "1",
        "PYAPP_FULL_ISOLATION": "1",
        "PYAPP_SKIP_INSTALL": "1",
        "PYAPP_IS_GUI": "1" if variant == "gui" else "0",
        "PYAPP_EXEC_SPEC": f"{LAUNCHER_MODULE}:main",
    }
    run(cargo, "build", "--release", env=env, cwd=source)
    return work / "pyapp-target" / "release" / f"pyapp{spec.executable_suffix}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--platform", choices=sorted(PLATFORMS), default=host())
    parser.add_argument("--variant", choices=["console", "gui"], default="console")
    parser.add_argument("--locks", type=Path, help="default: scripts/runtime/locks/<platform>")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "dist" / "runtime")
    parser.add_argument("--version", default=chronicler_version())
    args = parser.parse_args()

    if args.platform != host():
        raise SystemExit("The runtime has to be built on the platform it targets")

    started = time.monotonic()
    spec = PLATFORMS[args.platform]
    work = REPO_ROOT / "build" / "runtime" / args.platform
    cache = REPO_ROOT / "build" / "runtime" / "cache"
    locks = args.locks or LOCKS_DIR / args.platform
    if not (locks / "base.lock").is_file():
        raise SystemExit(f"No locks in {locks}; run scripts/runtime/locks.py")

    root = work / "runtime"
    shutil.rmtree(root, ignore_errors=True)
    log(f"unpacking CPython for {args.platform}")
    extract(fetch(PYTHON_RUNTIMES[args.platform], cache), root)
    python = root / spec.python_path.replace("\\", "/")
    site_packages = root / spec.site_packages.replace("\\", "/")

    log("installing the base dependencies from the lock")
    pip_install(python, "--require-hashes", "--only-binary", ":all:", "-r", locks / "base.lock")
    log("installing Chronicler")
    pip_install(python, build_wheel(work))

    log("adding the Flet client, component locks and launcher")
    install_flet_client(args.platform, python, root, cache)
    lock_target = root / "python" / "share" / "chronicler" / "locks"
    lock_target.mkdir(parents=True, exist_ok=True)
    for lock in locks.glob("component-*.lock"):
        shutil.copy2(lock, lock_target / lock.name)
    launcher = site_packages / f"{LAUNCHER_MODULE}.py"
    shutil.copy2(REPO_ROOT / "scripts" / "runtime" / "launcher.py", launcher)
    compileall.compile_file(str(launcher), quiet=1)

    trim(root, spec.trim)
    log("archiving the runtime")
    archive = archive_runtime(root, work)

    log(f"building the {args.variant} launcher")
    binary = build_launcher(args.platform, archive, args.variant, args.version, work, cache)
    args.out.mkdir(parents=True, exist_ok=True)
    target = args.out / f"Chronicler-{args.variant}{spec.executable_suffix}"
    shutil.copy2(binary, target)

    log(
        f"{target} ({target.stat().st_size / 1e6:.1f} MB, runtime archive "
        f"{archive.stat().st_size / 1e6:.1f} MB) in {time.monotonic() - started:.0f}s"
    )


if __name__ == "__main__":
    main()
