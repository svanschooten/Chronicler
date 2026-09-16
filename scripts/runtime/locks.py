#!/usr/bin/env python
"""
Maintains the hash-pinned requirement locks the embedded runtime is built from.

Everything is resolved together first, so a package shared between the base and a
component (or two components) gets one version everywhere. The base is then locked on
its own against those versions, and each component lock holds only what the base does
not already provide.

Existing pins are kept unless --upgrade is given, so regenerating after a pyproject.toml
change only moves what that change requires. --check fails when the committed locks are
out of date, which is what CI runs.

    python scripts/runtime/locks.py                   # refresh every platform
    python scripts/runtime/locks.py --upgrade         # move to the newest allowed versions
    python scripts/runtime/locks.py --check --platform linux
"""

import argparse
import difflib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.runtime.pins import COMPONENTS, PLATFORMS, PYTHON_VERSION  # noqa: E402

LOCKS_DIR = REPO_ROOT / "scripts" / "runtime" / "locks"
REQUIREMENT = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.\-]*)==(\S+)")

Blocks = dict[str, list[str]]


def uv() -> list[str]:
    found = shutil.which("uv")
    return [found] if found else [sys.executable, "-m", "uv"]


def lock_names() -> list[str]:
    return ["base.lock", *(f"component-{component}.lock" for component in COMPONENTS)]


def compile_lock(
    platform: str,
    output: Path,
    extras: list[str],
    constraints: Path | None = None,
    upgrade: bool = False,
) -> None:
    command = [
        *uv(),
        "pip",
        "compile",
        str(REPO_ROOT / "pyproject.toml"),
        "--generate-hashes",
        "--python-version",
        PYTHON_VERSION,
        "--python-platform",
        PLATFORMS[platform].uv_platform,
        "--only-binary",
        ":all:",
        "--no-header",
        "--quiet",
        "-o",
        str(output),
    ]
    for extra in extras:
        command += ["--extra", extra]
    if constraints is not None:
        command += ["-c", str(constraints)]
    if upgrade:
        command.append("--upgrade")
    subprocess.run(command, check=True)


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_blocks(text: str) -> Blocks:
    """Requirement blocks keyed by normalized name: the pin line plus its hash lines."""
    blocks: Blocks = {}
    current: str | None = None
    for line in text.splitlines():
        match = REQUIREMENT.match(line)
        if match:
            current = normalize(match.group(1))
            blocks[current] = [line.rstrip(" \\")]
        elif current is not None and line.strip().startswith("--hash="):
            blocks[current].append(line.strip().rstrip(" \\"))
        else:
            current = None
    return blocks


def render(blocks: Blocks) -> str:
    rendered = []
    for name in sorted(blocks):
        pin, *hashes = blocks[name]
        rendered.append(" \\\n    ".join([pin, *hashes]))
    return "\n".join(rendered) + "\n"


def without(blocks: Blocks, provided: Blocks) -> Blocks:
    return {name: block for name, block in blocks.items() if name not in provided}


def read_existing(directory: Path) -> Blocks:
    merged: Blocks = {}
    for name in lock_names():
        path = directory / name
        if path.is_file():
            merged.update(parse_blocks(path.read_text()))
    return merged


def generate(platform: str, existing: Path, upgrade: bool = False) -> dict[str, str]:
    """The rendered lock files for `platform`, keyed by file name."""
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        everything = work / "all.lock"
        seed = {} if upgrade else read_existing(existing)
        if seed:
            everything.write_text(render(seed))
        compile_lock(platform, everything, list(COMPONENTS), upgrade=upgrade)

        pins = work / "pins.txt"
        pinned = parse_blocks(everything.read_text())
        pins.write_text("\n".join(block[0] for block in pinned.values()))

        compile_lock(platform, work / "base.lock", [], constraints=pins)
        base = parse_blocks((work / "base.lock").read_text())
        rendered = {"base.lock": render(base)}

        for component in COMPONENTS:
            output = work / f"{component}.lock"
            compile_lock(platform, output, [component], constraints=pins)
            own = without(parse_blocks(output.read_text()), base)
            rendered[f"component-{component}.lock"] = render(own)
    return rendered


def differences(directory: Path, rendered: dict[str, str]) -> list[str]:
    changes: list[str] = []
    for name, text in rendered.items():
        path = directory / name
        current = path.read_text() if path.is_file() else ""
        if current != text:
            changes.extend(
                difflib.unified_diff(
                    current.splitlines(), text.splitlines(), str(path), f"{path} (expected)", n=0
                )
            )
    return changes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--platform", choices=sorted(PLATFORMS), action="append")
    parser.add_argument("--out", type=Path, help=f"default: {LOCKS_DIR.relative_to(REPO_ROOT)}")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="fail if the locks are out of date")
    mode.add_argument("--upgrade", action="store_true", help="move to the newest versions")
    args = parser.parse_args()

    stale = False
    for platform in args.platform or sorted(PLATFORMS):
        directory = (args.out or LOCKS_DIR) / platform
        rendered = generate(platform, directory, upgrade=args.upgrade)
        if args.check:
            changes = differences(directory, rendered)
            if changes:
                stale = True
                print(f"{platform}: locks are out of date", file=sys.stderr)
                print("\n".join(changes), file=sys.stderr)
            else:
                print(f"{platform}: locks are current")
            continue

        directory.mkdir(parents=True, exist_ok=True)
        for name, text in rendered.items():
            (directory / name).write_text(text)
        counts = ", ".join(f"{name} {text.count('==')}" for name, text in rendered.items())
        print(f"{platform}: {counts}")

    if stale:
        raise SystemExit("Run `python scripts/runtime/locks.py` and commit the result.")


if __name__ == "__main__":
    main()
