# 007-C2_worker_session_per_step

## One lock timeout stops all background work until restart

### info

| | |
| --- | --- |
| importance | critical |
| danger level | High: queued tasks silently never run. Change risk: medium, central code path. |
| reach | Full stack and server |
| effort | S |
| evidence | reproduced |
| touches | `chronicler/core/workers.py`, `chronicler/core/worker_wiring.py`, `chronicler/core/processing/handlers/base.py`, `chronicler/desktop/app.py`, `chronicler/server/main.py`, `tests/chronicler/core/test_workers.py`, `test_worker_wiring.py`, `tests/chronicler/desktop/test_app.py` |

### description

The worker holds one `AsyncSession` for the life of the process (`worker_wiring.py:30`).
When a write hits `database is locked` after SQLite's 5-second wait, SQLAlchemy marks that
session as needing a rollback. Nothing issues one. The failure path (`workers.py:80-83`)
uses the same dead session, the exception escapes, and `run_forever` (`workers.py:32-40`)
logs it and polls again, indefinitely. Nothing appears in the UI.

```text
first cycle after the lock                PendingRollbackError
interrupted task                          WORKING
next 5 polls, lock released               PendingRollbackError x 5
new task queued                           PENDING, 0 executed
same task, worker with a fresh session    DONE
```

Any write lock held for more than 5 seconds does this, including the speaker registry bug
and a second process on the same workspace.

### proposed fix

1. Give `WorkerManager` and `HandlerBase` a session factory rather than a session or
   repository. Open a short session for each group of repository calls, and hold none
   across a handler's run. This is how the RPC layer already scopes each request.
2. Make `update_progress` best effort: catch `OperationalError`, log it, and carry on.
3. Retry the final status write for a bounded time, so a lock at the wrong moment does not
   lose a finished result.
4. Remove `WorkerRuntime.session` and `DesktopApp._worker_session`. `server/main.py:53`
   never closed its session anyway.

Done when a test holds the write lock past the timeout during a task, and after release
that task finishes or returns to PENDING, a new task runs, and no `PendingRollbackError`
appears.

### related tickets

- (BLOCKER) [002-T2_two_connection_test_fixture](002-T2_two_connection_test_fixture.md): uses the two-connection fixture
- (BLOCKS) [009-C4_task_recovery](009-C4_task_recovery.md): same files, and the worker must survive errors before recovery means anything
- (BLOCKS) [040-S6_worker_and_handlers](040-S6_worker_and_handlers.md): changes how the worker gets sessions
- (RELATED) [006-C3_speaker_registry_commit](006-C3_speaker_registry_commit.md): that bug is the easiest way to trigger this one, but they can be fixed in either order
