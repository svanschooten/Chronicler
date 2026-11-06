import subprocess
import sys

import pytest

from chronicler.core.workspace_lock import WorkspaceLock, WorkspaceLockedError


def test_a_second_lock_on_one_workspace_is_refused(tmp_path):
    first = WorkspaceLock(tmp_path)
    first.acquire()
    try:
        with pytest.raises(WorkspaceLockedError, match="already open in another"):
            WorkspaceLock(tmp_path).acquire()
    finally:
        first.release()


def test_a_released_lock_can_be_taken_again(tmp_path):
    first = WorkspaceLock(tmp_path)
    first.acquire()
    first.release()

    second = WorkspaceLock(tmp_path)
    second.acquire()
    assert second.held
    second.release()


def test_acquire_twice_and_release_twice_are_noops(tmp_path):
    lock = WorkspaceLock(tmp_path)
    lock.acquire()
    lock.acquire()
    lock.release()
    lock.release()
    assert not lock.held


def test_acquire_creates_the_workspace(tmp_path):
    workspace = tmp_path / "new" / "workspace"
    lock = WorkspaceLock(workspace)
    lock.acquire()
    try:
        assert lock.path.exists()
    finally:
        lock.release()


def test_a_killed_process_does_not_block_the_next_start(tmp_path):
    """The OS drops the lock with the process, so no stale lock file can wedge startup."""
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys, time\n"
            "from pathlib import Path\n"
            "from chronicler.core.workspace_lock import WorkspaceLock\n"
            "WorkspaceLock(Path(sys.argv[1])).acquire()\n"
            "print('locked', flush=True)\n"
            "time.sleep(60)\n",
            str(tmp_path),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "locked"
        with pytest.raises(WorkspaceLockedError):
            WorkspaceLock(tmp_path).acquire()
    finally:
        holder.kill()
        holder.wait(timeout=10)

    lock = WorkspaceLock(tmp_path)
    lock.acquire()
    assert lock.held
    lock.release()
