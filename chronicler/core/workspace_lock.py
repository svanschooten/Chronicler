"""
One workspace belongs to one process at a time. See docs/storage.md.

The lock is an OS-level lock on a file in the workspace, so the OS releases it when the
process dies, however it dies. Nothing is left behind for the next start to clean up.
"""

import os
import sys
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


class WorkspaceLock:
    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path
        self.path = workspace_path / LOCK_FILE_NAME
        self._fd: int | None = None

    @property
    def held(self) -> bool:
        return self._fd is not None

    def acquire(self) -> None:
        """Takes the lock, or raises WorkspaceLockedError. A second call is a no-op."""
        if self._fd is not None:
            return

        self.workspace_path.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            _lock(fd)
        except OSError as error:
            os.close(fd)
            raise WorkspaceLockedError(self.workspace_path) from error
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

    def _lock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)

    def _unlock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)
