"""
One workspace belongs to one process at a time. See docs/storage.md.

The lock is an OS-level lock on a file in the workspace, so the OS releases it when the
process dies, however it dies. Nothing is left behind for the next start to clean up.
"""

import errno
import os
import sys
import tempfile
from pathlib import Path

LOCK_FILE_NAME = ".chronicler.lock"


class WorkspaceLockedError(RuntimeError):
    """Another process already has this workspace open."""

    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path
        super().__init__(
            f"The workspace at {workspace_path} is already open in another Chronicler "
            "process. Close that one first, or choose a different workspace."
        )


class WorkspaceLockUnavailableError(RuntimeError):
    """
    The lock could not be taken for a reason other than someone else holding it. Usually
    the workspace is on a network or FUSE mount that does not support file locks.
    """

    def __init__(self, workspace_path: Path, cause: OSError):
        self.workspace_path = workspace_path
        self.reason = cause.strerror or str(cause)
        super().__init__(
            f"Chronicler could not lock the workspace at {workspace_path}: {self.reason}. "
            "The filesystem it is on may not support file locks, as some network and "
            "FUSE mounts do not. Choose a workspace on a local disk."
        )


class WorkspaceNotWritableError(RuntimeError):
    """The workspace folder cannot be written to, so nothing could be stored in it."""

    def __init__(self, workspace_path: Path, cause: OSError):
        self.workspace_path = workspace_path
        self.reason = cause.strerror or str(cause)
        super().__init__(
            f"Chronicler cannot write to the workspace at {workspace_path}: {self.reason}. "
            "Check its permissions, or choose a different workspace."
        )


def probe_writable(path: Path) -> None:
    """
    Proves a folder can be written to by writing and removing a file in it. `os.access`
    cannot do this: on Windows it ignores ACLs and only looks at the read-only attribute.
    Raises OSError when the folder is missing, not a folder, or not writable.
    """
    with tempfile.TemporaryFile(dir=path):
        pass


class WorkspaceLock:
    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path
        self.path = workspace_path / LOCK_FILE_NAME
        self._fd: int | None = None

    @property
    def held(self) -> bool:
        return self._fd is not None

    def acquire(self) -> None:
        """
        Takes the lock. A second call is a no-op.

        Raises WorkspaceLockedError when another process holds it, and
        WorkspaceLockUnavailableError when the lock call fails for any other reason. Raises
        WorkspaceNotWritableError when the folder cannot be created or written to.
        """
        if self._fd is not None:
            return

        try:
            self.workspace_path.mkdir(parents=True, exist_ok=True)
            probe_writable(self.workspace_path)
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        except OSError as error:
            raise WorkspaceNotWritableError(self.workspace_path, error) from error
        try:
            _lock(fd)
        except OSError as error:
            os.close(fd)
            if error.errno in HELD_ELSEWHERE:
                raise WorkspaceLockedError(self.workspace_path) from error
            raise WorkspaceLockUnavailableError(self.workspace_path, error) from error
        self._fd = fd

    def release(self) -> None:
        if self._fd is None:
            return
        fd, self._fd = self._fd, None
        try:
            _unlock(fd)
        finally:
            os.close(fd)


if sys.platform == "win32":
    import msvcrt

    # What `msvcrt.locking` fails with when another process holds the region.
    HELD_ELSEWHERE = frozenset({errno.EACCES, errno.EDEADLOCK})

    def _lock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)

    def _unlock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    # What `flock` fails with when another process holds the lock. Anything else, such as
    # ENOLCK or EOPNOTSUPP, means the filesystem could not take a lock at all.
    HELD_ELSEWHERE = frozenset({errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES})

    def _lock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)
