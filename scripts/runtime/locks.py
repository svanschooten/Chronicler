#!/usr/bin/env python
"""
Generates the hash-pinned requirement locks the embedded runtime is built from.

Everything is resolved together first, so a package shared between the base and a
component (or two components) gets one version everywhere. The base is then locked on
its own against those versions, and each component lock holds only what the base does
not already provide.

    python scripts/runtime/locks.py --platform linux --out build/runtime/locks/linux
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.runtime.pins import COMPONENTS, PLATFORMS, PYTHON_VERSION  # noqa: E402

REQUIREMENT = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.\-]*)==(\S+)")


def uv() -> list[str]:
    found = shutil.which("uv")
    return [found] if found else [sys.executable, "-m", "uv"]


def compile_lock(
    platform: str, output: Path, extras: list[str], constraints: Path | None = None
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
    subprocess.run(command, check=True)


def parse_blocks(text: str) -> dict[str, list[str]]:
    """Requirement blocks keyed by normalized name: the pin line plus its hash lines."""
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        match = REQUIREMENT.match(line)
        if match:
            current = re.sub(r"[-_.]+", "-", match.group(1)).lower()
            blocks[current] = [line.rstrip(" \\")]
        elif current is not None and line.strip().startswith("--hash="):
            blocks[current].append(line.strip().rstrip(" \\"))
        else:
            current = None
    return blocks


def render(blocks: dict[str, list[str]]) -> str:
    rendered = []
    for name in sorted(blocks):
        pin, *hashes = blocks[name]
        rendered.append(" \\\n    ".join([pin, *hashes]))
    return "\n".join(rendered) + "\n"


def generate(platform: str, out: Path) -> dict[str, list[str]]:
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        compile_lock(platform, work / "all.lock", list(COMPONENTS))
        pins = work / "pins.txt"
        pins.write_text(
            "\n".join(block[0] for block in parse_blocks((work / "all.lock").read_text()).values())
        )

        compile_lock(platform, work / "base.lock", [], constraints=pins)
        base = parse_blocks((work / "base.lock").read_text())
        (out / "base.lock").write_text(render(base))

        summary = {"base": sorted(base)}
        for component in COMPONENTS:
            compile_lock(platform, work / f"{component}.lock", [component], constraints=pins)
            full = parse_blocks((work / f"{component}.lock").read_text())
            own = {name: block for name, block in full.items() if name not in base}
            (out / f"component-{component}.lock").write_text(render(own))
            summary[component] = sorted(own)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--platform", choices=sorted(PLATFORMS), required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    for name, packages in generate(args.platform, args.out).items():
        print(f"{name}: {len(packages)} packages")


if __name__ == "__main__":
    main()
