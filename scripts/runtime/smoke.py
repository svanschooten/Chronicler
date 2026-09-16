#!/usr/bin/env python
"""
Smoke-tests a built embedded-runtime executable headlessly.

Launches it twice (unpacking, then warm), checks it found its own Flet client, installs
every component from the locks it ships and transcribes a short sample with the tiny
Whisper model. Needs a console variant: a GUI launcher detaches and has no output.

    python scripts/runtime/smoke.py dist/runtime/Chronicler-console
    python scripts/runtime/smoke.py --subsystems dist/runtime
"""

import argparse
import struct
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.runtime.build import fetch  # noqa: E402
from scripts.runtime.pins import COMPONENTS, SMOKE_AUDIO  # noqa: E402

SUBSYSTEMS = {2: "GUI", 3: "console"}


def pe_subsystem(executable: Path) -> str:
    """The Windows subsystem an executable declares; a console one opens a window."""
    header = executable.read_bytes()[:4096]
    offset = struct.unpack_from("<I", header, 0x3C)[0]
    value = struct.unpack_from("<H", header, offset + 24 + 68)[0]
    return SUBSYSTEMS.get(value, f"subsystem {value}")


def step(title: str) -> None:
    print(f"\n== {title}", flush=True)


def run(binary: Path, *arguments: str) -> str:
    completed = subprocess.run(
        [str(binary), *arguments], capture_output=True, text=True, encoding="utf-8"
    )
    output = completed.stdout + completed.stderr
    print(output.rstrip(), flush=True)
    if completed.returncode != 0:
        raise SystemExit(f"`{binary.name} {' '.join(arguments)}` exited {completed.returncode}")
    return output


def smoke(binary: Path, cache: Path) -> None:
    for launch in ("first", "warm"):
        step(f"{launch} launch")
        started = time.monotonic()
        run(binary, "--help")
        print(f"{launch} launch took {time.monotonic() - started:.2f}s")

    step("runtime layout")
    if "flet_client=None" in run(binary, "components", "where"):
        raise SystemExit("The runtime did not find the Flet client it ships")

    step("component install")
    run(binary, "components", "install", *COMPONENTS)

    step("transcription")
    audio = fetch(SMOKE_AUDIO, cache)
    if "transcribed 0 lines" in run(binary, "components", "smoke", str(audio)):
        raise SystemExit("The sample produced no transcript")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("binary", type=Path, nargs="?")
    parser.add_argument("--subsystems", type=Path, metavar="DIR", help="report .exe subsystems")
    parser.add_argument("--cache", type=Path, default=REPO_ROOT / "build" / "runtime" / "cache")
    args = parser.parse_args()

    if args.subsystems:
        for executable in sorted(args.subsystems.glob("*.exe")):
            print(f"{executable.name}: {pe_subsystem(executable)}")
    if args.binary:
        smoke(args.binary.resolve(), args.cache)


if __name__ == "__main__":
    main()
