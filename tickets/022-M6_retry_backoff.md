# 022-M6_retry_backoff

## Retries run about one second apart

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Medium: an outage burns all attempts, while a late transcription failure repeats for hours. Change risk: low, adds a migration. |
| reach | Full stack and server |
| effort | S |
| evidence | reproduced |
| touches | `chronicler/core/database.py`, `chronicler/core/models.py`, new migration in `chronicler/migrations/archive/`, `chronicler/core/sqlite/task_repository.py`, `chronicler/core/workers.py`, `chronicler/core/services/task_service.py`, `chronicler/desktop/views/tasks.py`, `docs/tasks.md` |

### description

A failing task used all three attempts with gaps of 1.03 s and 1.02 s, then went to
FAILED. `docs/tasks.md:30-37` justifies the bounded loop in `process_tasks` as giving a
transient failure time to clear, and one second will not cover a gateway restart.

In the other direction, a transcription that fails near the end runs in full three times.

### proposed fix

1. Add a `not_before` column to `tasks`. `mark_failed_or_retry` sets it with backoff, for
   example 30 seconds and then 5 minutes. `claim_next` skips rows that are not due yet,
   and `retry_task` clears it.
2. Set `max_attempts` per task type in `TaskService`: 1 for TRANSCRIBE, because a rerun is
   expensive and manual retry exists.
3. Remove the bounded loop in `process_tasks`, which backoff makes unnecessary.
4. Show the next attempt time in the Tasks view, and update `docs/tasks.md`.

Done when a failing task's attempts are spaced by the configured delays.

### related tickets

- (BLOCKER) [009-C4_task_recovery](009-C4_task_recovery.md): same repository and worker code
- (BLOCKS) [040-S6_worker_and_handlers](040-S6_worker_and_handlers.md): changes what `claim_next` selects
- (BLOCKS) [064-F2_progress_and_cancel](064-F2_progress_and_cancel.md): cancel must not be retried
- (RELATED) [050-L6_recap_budget](050-L6_recap_budget.md): per-type attempts also limit repeated paid summary runs
