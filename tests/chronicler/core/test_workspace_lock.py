import errno
import os
import subprocess
import sys

import pytest

from chronicler.core import workspace_lock
from chronicler.core.workspace_lock import (
    WorkspaceLock,
    WorkspaceLockedError,
    WorkspaceLockUnavailableError,
    WorkspaceNotWritableError,
)


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


def _failing_with(monkeypatch, code: int) -> None:
    def fail(fd: int) -> None:
        raise OSError(code, os.strerror(code))

    monkeypatch.setattr(workspace_lock, "_lock", fail)


@pytest.mark.parametrize("code", sorted(workspace_lock.HELD_ELSEWHERE))
def test_a_lock_someone_else_holds_reads_as_already_open(tmp_path, monkeypatch, code):
    _failing_with(monkeypatch, code)

    with pytest.raises(WorkspaceLockedError, match="already open in another"):
        WorkspaceLock(tmp_path).acquire()


@pytest.mark.parametrize("code", [errno.ENOLCK, errno.EINVAL, errno.EOPNOTSUPP, errno.EIO])
def test_a_filesystem_that_cannot_lock_is_not_reported_as_in_use(tmp_path, monkeypatch, code):
    """Ticket 068: on some NFS, SMB and FUSE mounts every start read as "already open"."""
    _failing_with(monkeypatch, code)
    lock = WorkspaceLock(tmp_path)

    with pytest.raises(WorkspaceLockUnavailableError) as raised:
        lock.acquire()

    message = str(raised.value)
    assert "already open" not in message
    assert str(tmp_path) in message
    assert os.strerror(code) in message
    assert "local disk" in message
    assert raised.value.workspace_path == tmp_path
    assert not isinstance(raised.value, WorkspaceLockedError)
    assert not lock.held


def test_a_failed_lock_does_not_leak_its_file_descriptor(tmp_path, monkeypatch):
    closed = []
    real_close = os.close
    monkeypatch.setattr(os, "close", lambda fd: (closed.append(fd), real_close(fd))[1])
    _failing_with(monkeypatch, errno.ENOLCK)

    with pytest.raises(WorkspaceLockUnavailableError):
        WorkspaceLock(tmp_path).acquire()

    assert len(closed) == 1


def test_a_workspace_that_cannot_be_written_is_reported_as_such(tmp_path, monkeypatch):
    def refuse(*args, **kwargs):
        raise PermissionError(errno.EACCES, os.strerror(errno.EACCES))

    monkeypatch.setattr(workspace_lock.tempfile, "TemporaryFile", refuse)
    lock = WorkspaceLock(tmp_path)

    with pytest.raises(WorkspaceNotWritableError) as raised:
        lock.acquire()

    assert str(tmp_path) in str(raised.value)
    assert os.strerror(errno.EACCES) in str(raised.value)
    assert not lock.held


def test_a_workspace_path_that_is_a_file_is_reported_as_not_writable(tmp_path):
    a_file = tmp_path / "file"
    a_file.write_text("x")

    with pytest.raises(WorkspaceNotWritableError):
        WorkspaceLock(a_file).acquire()


def test_the_probe_leaves_nothing_behind(tmp_path):
    workspace_lock.probe_writable(tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_a_workspace_path_that_is_a_file_says_it_is_not_a_folder(tmp_path):
    a_file = tmp_path / "file"
    a_file.write_text("x")

    with pytest.raises(WorkspaceNotWritableError) as raised:
        WorkspaceLock(a_file).acquire()

    assert raised.value.reason == os.strerror(errno.ENOTDIR)
