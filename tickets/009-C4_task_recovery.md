# 009-C4_task_recovery

## Interrupted tasks stay WORKING forever

### info

| | |
| --- | --- |
| importance | critical |
| danger level | High: work silently stops, and the UI offers no way out. Change risk: low. |
| reach | Full stack and server, after any crash and, from the code, after a normal close during a task |
| effort | S |
| evidence | reproduced |
| touches | `chronicler/core/sqlite/task_repository.py`, `chronicler/core/repositories.py`, `chronicler/core/workers.py`, `docs/tasks.md` |

### description

`claim_next` (`task_repository.py:59-82`) only looks at PENDING rows, and nothing ever
returns an abandoned WORKING row. The Tasks view offers retry only for DONE and FAILED
(`tasks.py:16`), so the row cannot be rescued from the UI.

```text
status after restart             WORKING
claimed_by                       worker-that-crashed
UI offers retry for this status  no
```

From the code, a normal app close does the same: `DesktopApp.cleanup` cancels the worker
(`app.py:154`), and `CancelledError` skips the failure path in `_execute_task`. The README
says tasks survive restarts.

### proposed fix

1. Add `recover_interrupted()` to the task repository and call it when the worker starts.
   It returns WORKING rows to PENDING, clears `claimed_by` and `claimed_at`, resets
   progress and records "Interrupted before finishing".
2. Count that as an attempt, and mark the task FAILED once attempts run out, so a task
   that crashes the process each time cannot loop forever.
3. On a graceful stop, catch `CancelledError` in `_execute_task`, return the task to
   PENDING without using an attempt, and re-raise.
4. If a recovered TRANSCRIBE or NORMALIZE ends up FAILED, also clear `RUNNING` on its
   audio source, or the Sources panel keeps saying it is transcribing.

The audit report also suggested offering retry on WORKING rows. With this reset, a visible
WORKING row really is running, so a retry would run it twice. Leave that out.

Since 007-C2, a task can also stay WORKING without a crash: when its final status write
is still locked after `STATUS_WRITE_TIMEOUT`, the error propagates and the row keeps
WORKING. The startup reset covers that row too, so no extra work is needed, but it is
another way to reach the state this fixes.

Done when killing the process mid-task and restarting runs the task again, and closing the
app mid-task leaves it PENDING.

### related tickets

- (BLOCKER) [007-C2_worker_session_per_step](007-C2_worker_session_per_step.md): same files, and the worker must survive errors before recovery means anything
- (BLOCKER) [008-A1_single_process_workspace_lock](008-A1_single_process_workspace_lock.md): resetting at startup is only safe with one process per workspace
- (BLOCKS) [022-M6_retry_backoff](022-M6_retry_backoff.md): same repository and worker code
- (BLOCKS) [040-S6_worker_and_handlers](040-S6_worker_and_handlers.md): edits the same repository
- (BLOCKS) [064-F2_progress_and_cancel](064-F2_progress_and_cancel.md): cancel must interact correctly with task recovery
- (RELATED) [069-L12_completion_event_on_busy_database](069-L12_completion_event_on_busy_database.md): same file, take it after this one
