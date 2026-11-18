"""
Fixtures for the rendered UI tests: the real desktop app, drawn by a real Flutter client.

These tests need Flutter, a display and the client `scripts/ui_host.py` prepares, so they
are only collected when `FLET_TEST_FLUTTER_APP_DIR` points at that client. The ordinary
`pytest` run leaves them out. See docs/testing.md.
"""

import json
import os
import shutil
import socket
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from chronicler.core.config import Mode, Settings
from chronicler.core.models import Chronicle, Task, TaskType
from chronicler.core.processing.handlers import WorkerHandlers
from chronicler.core.sqlite import SQLiteChronicleRepository
from chronicler.desktop.app import DesktopApp
from chronicler.desktop.runtime import build_runtime

HOST_ENV_VAR = "FLET_TEST_FLUTTER_APP_DIR"
SCREENSHOTS_ENV_VAR = "CHRONICLER_UI_SCREENSHOTS"
"""A folder to save a grab of the screen to when a test fails. Unset, nothing is saved."""

UNKNOWN_CONTROL = "Unknown control"
"""What the Flutter client draws for a control it cannot render, such as a FilePicker in
`page.overlay`. A control-tree test cannot see it."""

CHRONICLE_TITLE = "Seeded Session"
SHORT_LINE = "General Kenobi."
LONG_LINE = " ".join(["This line is long enough to wrap, so its middle is always text."] * 6)
"""Long enough to fill the transcript's width, so a tap on the middle of it lands on text."""

if not os.environ.get(HOST_ENV_VAR):
    collect_ignore_glob = ["test_*.py"]
else:
    # Every test points HOME at a temporary folder (`isolated_config`), and Flutter keeps
    # its package cache under HOME. Without this each test would download every Dart
    # package again into a folder pytest later deletes, and the build would break once it
    # had. Set only here, so the ordinary run's environment is left alone.
    os.environ.setdefault("PUB_CACHE", str(Path.home() / ".pub-cache"))


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    report = yield
    if report.when == "call":
        item.ui_failed = report.failed
    return report


def _grab_screen(name: str) -> None:
    """Flet takes app screenshots only on Android and iOS, so grab the X display instead."""
    folder = os.environ.get(SCREENSHOTS_ENV_VAR)
    if not folder or not shutil.which("ffmpeg") or not os.environ.get("DISPLAY"):
        return
    Path(folder).mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "x11grab", "-i", os.environ["DISPLAY"]]
        + ["-frames:v", "1", str(Path(folder, f"{name}.png"))],
        check=False,
    )


def _free_port() -> int:
    """
    A port for the app to listen on. Flet finds one itself by binding a socket it never
    closes, which the suite's ResourceWarning filter turns into an error.
    """
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


async def _noop(_progress) -> None:
    return None


async def _seed(runtime) -> Chronicle:
    """One chronicle with a short imported transcript, imported the way the app does it."""
    db = runtime.db_manager
    await db.init_archive()
    async with db.get_archive_session() as session:
        chronicle = await SQLiteChronicleRepository(session).create(
            Chronicle(title=CHRONICLE_TITLE, description="A chronicle for the UI tests")
        )
    staged = db.get_imports_path() / "seed.txt"
    staged.write_text(
        f"Alice: Hello there.\nBob: {SHORT_LINE}\nAlice: {LONG_LINE}\n", encoding="utf-8"
    )
    task = Task(
        type=TaskType.IMPORT,
        chronicle_id=chronicle.id,
        data=json.dumps({"file_path": str(staged)}),
    )
    await WorkerHandlers(db).handle_import(task, _noop)
    return chronicle


@pytest.fixture
def runtime(tmp_path, isolated_config):
    return build_runtime(Settings(workspace_path=tmp_path / "workspace", mode=Mode.FULL_STACK))


@pytest_asyncio.fixture
async def tester(request, runtime) -> AsyncIterator:
    """
    Starts the app on a seeded workspace and connects the Flutter client to it.

    Every test also fails if the client drew an "Unknown control" at the end.
    """
    import flet.testing as ftt

    await _seed(runtime)
    desktop = DesktopApp(runtime)
    app_errors: list[BaseException] = []

    async def main(page) -> None:
        # Flet logs an exception from the app's main and closes the session, which ends
        # the client; the test would only see "Flutter process exited early".
        try:
            await desktop.main(page)
        except BaseException as error:
            app_errors.append(error)
            raise

    app = ftt.FletTestApp(
        flutter_app_dir=Path(os.environ[HOST_ENV_VAR]),
        flet_app_main=main,
        test_path=str(request.path),
        tcp_port=_free_port(),
        device_mode=False,
        disable_fvm=True,
    )
    started = False
    try:
        try:
            await app.start()
        except RuntimeError as error:
            if app_errors:
                raise app_errors[0] from error
            raise
        started = True
        await app.tester.pump_and_settle()
        yield app.tester
        await app.tester.pump_and_settle()
        unknown = await app.tester.find_by_text_containing(UNKNOWN_CONTROL)
        if unknown.count or getattr(request.node, "ui_failed", False):
            _grab_screen(request.node.name)
        assert unknown.count == 0, "the client drew a control it could not render"
    finally:
        if started:
            await app.teardown()
        await runtime.db_manager.close_all()
