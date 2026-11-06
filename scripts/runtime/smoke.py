#!/usr/bin/env python
"""
Smoke-tests a built embedded-runtime executable headlessly.

Launches it twice (unpacking, then warm), checks it found its own Flet client, installs
every component from the locks it ships, transcribes a short sample with the tiny Whisper
model and starts a server it then pings. Needs a console variant: a GUI launcher detaches
and has no output.

    python scripts/runtime/smoke.py dist/runtime/Chronicler-console
    python scripts/runtime/smoke.py --subsystems dist/runtime
"""

import argparse
import json
import secrets
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.runtime.build import fetch  # noqa: E402
from scripts.runtime.pins import COMPONENTS, SMOKE_AUDIO  # noqa: E402

SUBSYSTEMS = {2: "GUI", 3: "console"}
SERVER_START_TIMEOUT = 90.0


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

    step("server")
    ping_server([str(binary)])


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def ping(port: int, api_key: str) -> str | None:
    """The server's answer to /system/ping, or None while it is not listening yet."""
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/system/ping",
        data=b"{}",
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    # No proxy: a developer's HTTP_PROXY would otherwise get the request for 127.0.0.1.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=5) as response:
            return json.loads(response.read())
    except (urllib.error.URLError, ConnectionError, TimeoutError):
        return None


def ping_server(command: list[str], timeout: float = SERVER_START_TIMEOUT) -> None:
    """
    Starts `command server` on a free port with a throwaway config and workspace, and
    waits for /system/ping to answer. A build without the server component exits instead.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as scratch:
        root = Path(scratch)
        api_key = secrets.token_urlsafe(16)
        config = root / "settings.json"
        config.write_text(
            json.dumps(
                {"mode": "server", "workspace_path": str(root / "workspace"), "api_key": api_key}
            )
        )
        port = free_port()
        log = root / "server.log"
        with log.open("w", encoding="utf-8") as output:
            server = subprocess.Popen(
                [*command, "--config", str(config), "server", "--host", "127.0.0.1"]
                + ["--port", str(port)],
                cwd=root,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
            try:
                answer, started = None, time.monotonic()
                while answer is None and server.poll() is None:
                    if time.monotonic() - started > timeout:
                        break
                    answer = ping(port, api_key)
                    if answer is None:
                        time.sleep(0.5)
            finally:
                server.terminate()
                try:
                    server.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()
        print(log.read_text(encoding="utf-8", errors="replace").rstrip(), flush=True)

    if answer != "ok":
        raise SystemExit(f"The server did not answer /system/ping (got {answer!r})")
    print(f"server answered ping in {time.monotonic() - started:.1f}s", flush=True)


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
