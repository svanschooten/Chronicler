# 068-M12_workspace_lock_error_reasons

## Any failure to lock a workspace reads as "already open in another process"

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Medium: on a filesystem without lock support Chronicler can never open the workspace, and the message points the wrong way. Change risk: very low. |
| reach | Full stack and server, on network or FUSE-mounted workspaces |
| effort | XS |
| evidence | read in code |
| touches | `chronicler/core/workspace_lock.py`, `chronicler/core/database_manager.py`, `docs/troubleshooting.md`, `docs/storage.md`, `tests/chronicler/core/test_workspace_lock.py` |

### description

Found while reviewing 008-A1. `WorkspaceLock.acquire` (`workspace_lock.py:36-48`) turns
every `OSError` from `fcntl.flock` or `msvcrt.locking` into `WorkspaceLockedError`.
`flock` also fails with `ENOLCK`, `EINVAL` or `EOPNOTSUPP` on some NFS, SMB and FUSE
mounts. There, every start reports "already open in another Chronicler process", and
`docs/troubleshooting.md:158` says that message "always means a running process".

Two smaller gaps in the same code:

- `init_archive` creates `imports/` (`database_manager.py:60`) after taking the lock and
  outside the `try` that releases it, so a failure there keeps the lock held.
- After `close_all()` releases the lock, the engines reconnect on next use, so a manager
  used after closing works without the lock.

### proposed fix

1. Raise `WorkspaceLockedError` only for "held by someone else": `EWOULDBLOCK`/`EAGAIN`
   (and `EACCES`) on POSIX, and `EACCES`/`EDEADLOCK` from `msvcrt.locking`. Raise any
   other error as a new `WorkspaceLockUnavailableError` naming the filesystem problem.
2. Show that reason through the same desktop startup screen and server exit as
   `WorkspaceLockedError`.
3. Move the `imports/` mkdir inside the `try`.
4. Correct `docs/troubleshooting.md` and `docs/storage.md`.

Whether a manager should refuse to work after `close_all()` is optional here: today
nothing reuses one.

Done when a test that makes the lock call fail with `ENOLCK` gets the new error and
message, and one that fails with `EWOULDBLOCK` still gets `WorkspaceLockedError`.

### related tickets

- (RELATED) [008-A1_single_process_workspace_lock](008-A1_single_process_workspace_lock.md): introduced the lock
- (RELATED) [055-L11_workspace_validation](055-L11_workspace_validation.md): reports through the same startup path
