# 008-A1_single_process_workspace_lock

## Nothing stops two processes from sharing a workspace

### info

| | |
| --- | --- |
| importance | high |
| danger level | Medium: lock contention, and task recovery would run tasks twice. Change risk: low. |
| reach | Full stack and server |
| effort | S |
| evidence | read in code |
| touches | `chronicler/core/database_manager.py`, `chronicler/desktop/main.py`, `chronicler/server/main.py`, `README.md`, `ARCHITECTURE.md`, `docs/tasks.md` |

### description

Decision from the audit: one workspace belongs to one process at a time. Today nothing
enforces this, and `docs/tasks.md:66-68` and `ARCHITECTURE.md:392-395` describe several
processes sharing a workspace as a supported case.

Supporting that properly would need task leases and heartbeats. Ruling it out lets task
recovery be a simple reset at startup.

The README also suggests storing a workspace in Dropbox. A local lock cannot protect
against two machines opening a synced copy at once, so that needs a warning.

### proposed fix

1. Take an exclusive OS-level lock on a file in the workspace when the archive opens, and
   release it in `close_all`. A small helper over `msvcrt.locking` and `fcntl.flock` is
   enough, or the `filelock` package. The OS frees the lock if the process dies.
2. On failure, the desktop shows the reason with `show_startup_failure`, and the server
   exits with a clear message.
3. Update `docs/tasks.md` and `ARCHITECTURE.md`, and add the warning about synced
   workspaces to the README.

Done when starting a second process on one workspace fails with a readable message, and a
killed process does not block the next start.

### related tickets

- (BLOCKS) [009-C4_task_recovery](009-C4_task_recovery.md): resetting at startup is only safe with one process per workspace
- (RELATED) [055-L11_workspace_validation](055-L11_workspace_validation.md): reports failure through the same startup path
