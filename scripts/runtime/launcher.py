"""
Entry point of the embedded runtime, installed into it as `chronicler_launcher`.

Before Chronicler starts it puts the installed components on the import path and points
Flet at the client shipped inside the runtime. `components` is a small command line for
installing components from the locks the build embedded; it stands in for the component
manager until that is part of the app itself.
"""

import hashlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

SHARE = Path(sys.prefix) / "share"
LOCKS = SHARE / "chronicler" / "locks"
FLET_CLIENT = SHARE / "flet-client"


def components_root() -> Path:
    import platformdirs

    return platformdirs.user_data_path("Chronicler", appauthor=False) / "components"


def lock_files(names: list[str]) -> list[Path]:
    paths = [LOCKS / f"component-{name}.lock" for name in sorted(set(names))]
    missing = [path.name for path in paths if not path.is_file()]
    if missing:
        raise SystemExit(f"unknown component(s): {', '.join(missing)}")
    return paths


def set_key(names: list[str]) -> str:
    digest = hashlib.sha256()
    for path in lock_files(names):
        digest.update(path.name.encode() + path.read_bytes())
    return f"cp{sys.version_info.major}{sys.version_info.minor}-{digest.hexdigest()[:16]}"


def active_dir() -> Path | None:
    pointer = components_root() / "active"
    if not pointer.is_file():
        return None
    target = components_root() / pointer.read_text().strip()
    return target if target.is_dir() else None


def activate() -> None:
    target = active_dir()
    if target is not None and str(target) not in sys.path:
        sys.path.append(str(target))
    if FLET_CLIENT.is_dir() and not os.environ.get("FLET_VIEW_PATH"):
        os.environ["FLET_VIEW_PATH"] = str(FLET_CLIENT)


def install(names: list[str]) -> int:
    root = components_root()
    root.mkdir(parents=True, exist_ok=True)
    key = set_key(names)
    final = root / key
    if final.is_dir():
        print(f"already installed: {key}")
    else:
        staging = root / f".staging-{key}"
        shutil.rmtree(staging, ignore_errors=True)
        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--isolated",
            "--disable-pip-version-check",
            "--no-warn-script-location",
            "--require-hashes",
            "--no-deps",
            "--only-binary",
            ":all:",
            "--target",
            str(staging),
        ]
        for path in lock_files(names):
            command += ["-r", str(path)]
        started = time.monotonic()
        result = subprocess.run(command)
        if result.returncode != 0:
            shutil.rmtree(staging, ignore_errors=True)
            return result.returncode
        staging.rename(final)
        print(f"installed {key} in {time.monotonic() - started:.1f}s")
    (root / "active").write_text(key)
    return 0


def smoke(audio: str) -> int:
    activate()
    from chronicler.core import extras

    for name in ("transcription", "normalization", "recording"):
        print(f"{name}: available={extras.is_available(name)}")
    if not extras.is_available("transcription"):
        return 1

    from chronicler.core.processing.transcriber import transcribe_audio

    started = time.monotonic()
    lines = transcribe_audio(audio, "Smoke", model_size="tiny", device="cpu", compute_type="int8")
    print(f"transcribed {len(lines)} lines in {time.monotonic() - started:.1f}s")
    for line in lines[:4]:
        print(f"  [{line.start_time:5.1f}-{line.end_time:5.1f}] {line.text}")
    return 0 if lines else 1


def where() -> int:
    print(f"prefix={sys.prefix}")
    print(f"executable={sys.executable}")
    print(f"flet_client={FLET_CLIENT if FLET_CLIENT.is_dir() else None}")
    print(f"components={active_dir()}")
    return 0


def main() -> None:
    args = sys.argv[1:]
    if args[:1] == ["components"]:
        action, rest = (args[1], args[2:]) if len(args) > 1 else ("where", [])
        if action == "install":
            raise SystemExit(install(rest))
        if action == "smoke" and rest:
            raise SystemExit(smoke(rest[0]))
        if action == "where":
            raise SystemExit(where())
        raise SystemExit("usage: components install <name>... | smoke <audio> | where")

    activate()
    from chronicler.__main__ import main as chronicler_main

    chronicler_main()
