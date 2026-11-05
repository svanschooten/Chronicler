# 064-F2_progress_and_cancel

## Real transcription progress and cancel

### info

| | |
| --- | --- |
| importance | medium |
| danger level | None: a missing feature. Long runs give no feedback and cannot be stopped. Change risk: medium. |
| reach | Anyone transcribing |
| effort | M |
| evidence | read in code |
| touches | `chronicler/core/processing/transcriber.py`, `chronicler/core/processing/handlers/transcribing.py`, `chronicler/core/models.py`, `chronicler/core/workers.py`, `chronicler/core/services/task_service.py`, `chronicler/desktop/views/tasks.py` |

### description

Progress jumps from 30 to 70 with nothing in between (`transcribing.py:84-93`), and a task
cannot be stopped. The Tasks view never refreshes while a task runs, and thin clients get
no live updates at all.

faster-whisper yields segments lazily, so the loop at `transcriber.py:62` already sees
each one as it is produced.

### proposed fix

1. Report `segment.end / info.duration` from that loop, passing it back to the event loop
   safely.
2. Check a cancel flag in the same loop. Add a `CANCELLED` status and
   `TaskService.cancel_task`.
3. Have the Tasks view poll every 2 seconds while a row is WORKING. This also works on
   thin clients.
4. Stop the Tasks view rebuilding on completion if the view-refresh ticket has not
   already.

Done when progress moves during a real transcription, and cancel stops it within a
segment.

### related tickets

- (BLOCKER) [009-C4_task_recovery](009-C4_task_recovery.md): cancel must interact correctly with task recovery
- (BLOCKER) [022-M6_retry_backoff](022-M6_retry_backoff.md): cancel must not be retried
- (BLOCKER) [040-S6_worker_and_handlers](040-S6_worker_and_handlers.md): same handler code
- (RELATED) [027-M7_refresh_view_in_place](027-M7_refresh_view_in_place.md): both change how the Tasks view refreshes
