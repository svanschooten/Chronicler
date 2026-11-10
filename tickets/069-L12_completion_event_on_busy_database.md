# 069-L12_completion_event_on_busy_database

## A finished task's event is lost when the database is busy

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: the view does not refresh after a task, until the next navigation. Change risk: very low. |
| reach | Full stack and server |
| effort | XS |
| evidence | read in code |
| touches | `chronicler/core/workers.py`, `tests/chronicler/core/test_workers.py` |

### description

Found while reviewing 007-C2. After a task's final status is written, which retries for
up to `STATUS_WRITE_TIMEOUT`, `_publish_completion` (`workers.py:135`) reads the task back
on a new session to build the event. That read has no retry and no error handling. If it
hits "database is locked", the exception leaves `_execute_task` (`workers.py:112`), the
event is never published, and the open view keeps showing the task as running.

### proposed fix

Build the event from what the worker already knows instead of reading it back:
`_record_outcome` can return the final status, and the task already carries
`chronicle_id`. If a read-back stays, give it the same bounded retry and log a failure
rather than raising.

Done when a test holding the write lock across `_publish_completion` still receives the
`TaskCompletedEvent`.

### related tickets

- (RELATED) [007-C2_worker_session_per_step](007-C2_worker_session_per_step.md): added the retry this leaves out
- (RELATED) [027-M7_refresh_view_in_place](027-M7_refresh_view_in_place.md): consumes the event
- (RELATED) [009-C4_task_recovery](009-C4_task_recovery.md): same file; take this after it
