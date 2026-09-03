#!/usr/bin/env python
"""
Boots a real Chronicler server and connects a real thin client to it.

Both processes get their own isolated config via CHRONICLER_CONFIG_FILE, so this never
touches your own configuration. See docs/thin-client-testing.md.

    python scripts/thin_client_check.py
    python scripts/thin_client_check.py --host 0.0.0.0 --port 8000 --keep-running
"""

import argparse
import asyncio
import contextlib
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from chronicler import __version__  # noqa: E402
from chronicler.core.handshake import HandshakeError, perform_handshake  # noqa: E402
from chronicler.core.remote import RemoteContainer  # noqa: E402
from chronicler.core.services import ChronicleService  # noqa: E402

API_KEY = "thin-client-check-key"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _write_config(path: Path, **values) -> Path:
    path.write_text(yaml.dump(values))
    return path


def _wait_for_port(host: str, port: int, process: subprocess.Popen, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    probe_host = "127.0.0.1" if host == "0.0.0.0" else host
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        with contextlib.suppress(OSError), socket.create_connection((probe_host, port), 0.5):
            return True
        time.sleep(0.2)
    return False


async def _run_client(url: str) -> int:
    remote = RemoteContainer(url, api_key=API_KEY)
    try:
        result = await perform_handshake(remote)
    except HandshakeError as error:
        print(f"  FAIL  handshake: {error}")
        return 1

    print(f"  ok    server version {result.server_info.version} matches client {__version__}")
    print(f"  ok    capabilities: {', '.join(result.server_info.capabilities)}")
    print(f"  ok    pulled chronicle list ({result.chronicle_count} chronicles)")

    chronicles = remote.resolve(ChronicleService)
    created = await chronicles.create_chronicle("Thin client check")
    listed = await chronicles.list_chronicles()
    if not any(item.id == created.id for item in listed):
        print("  FAIL  created chronicle did not come back in the listing")
        return 1
    print(f"  ok    round-tripped a chronicle over RPC ({created.title})")

    await chronicles.delete_chronicle(created.id)
    print("  ok    cleaned up")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Address the server binds to")
    parser.add_argument("--port", type=int, default=0, help="Server port (0 picks a free one)")
    parser.add_argument("--timeout", type=float, default=60.0, help="Seconds to wait for startup")
    parser.add_argument(
        "--keep-running",
        action="store_true",
        help="Leave the server up after the check, for connecting from another device",
    )
    args = parser.parse_args()

    port = args.port or _free_port()
    workdir = Path(tempfile.mkdtemp(prefix="chronicler-thin-check-"))
    workspace = workdir / "workspace"
    workspace.mkdir(parents=True)

    server_config = _write_config(
        workdir / "server.yaml",
        workspace_path=str(workspace),
        api_key=API_KEY,
        mode="server",
    )
    url = f"http://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{port}"
    _write_config(
        workdir / "client.yaml",
        server_url=url,
        api_key=API_KEY,
        mode="desktop:thin_client",
    )

    print(f"Chronicler {__version__} thin-client check")
    print(f"  workdir: {workdir}")
    print(f"  server:  {args.host}:{port}")

    env = {**os.environ, "CHRONICLER_CONFIG_FILE": str(server_config), "PYTHONUNBUFFERED": "1"}
    server = subprocess.Popen(
        [sys.executable, "-m", "chronicler", "server", "--host", args.host, "--port", str(port)],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        print("\nStarting server...")
        if not _wait_for_port(args.host, port, server, args.timeout):
            print("  FAIL  server did not start listening")
            if server.stdout:
                print(server.stdout.read())
            return 1
        print("  ok    server is listening")

        print("\nConnecting thin client...")
        exit_code = asyncio.run(_run_client(url))

        if exit_code == 0:
            print("\nPASS - the thin client can talk to the server.")
        if args.keep_running:
            print(f"\nServer still running on {args.host}:{port}. Ctrl-C to stop.")
            print(f"Point another device at http://<this-machine-ip>:{port} with API key {API_KEY}")
            with contextlib.suppress(KeyboardInterrupt):
                server.wait()
        return exit_code
    finally:
        if not args.keep_running:
            server.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                server.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
