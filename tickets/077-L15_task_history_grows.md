# 077-L15_task_history_grows

## The task list keeps every task ever run

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: the Tasks view gets slower over months, most on thin clients. Change risk: low. |
| reach | All modes |
| effort | S |
| evidence | read in code |
| touches | `chronicler/core/sqlite/task_repository.py`, `chronicler/core/services/task_service.py`, `chronicler/desktop/views/tasks.py`, `chronicler/i18n/messages/`, `tests/chronicler/core/sqlite/test_task_repository.py`, `tests/chronicler/desktop/views/test_tasks.py`, `docs/tasks.md` |

### description

Found in the review after wave 4.

Nothing deletes a finished task except deleting its chronicle. `TaskService.list_tasks`
(`task_service.py:36-37`) returns every row, payloads included, and the Tasks view
(`tasks.py:108-110`) filters out finished ones afterwards. On a thin client the whole
history crosses the network on every refresh, and 064's polling would repeat that every
2 seconds.

### proposed fix

1. Filter on the server: `list_tasks(include_finished: bool = False)`, and return
   finished tasks newest first with a limit.
2. Add *Clear finished tasks*, deleting DONE rows, and FAILED rows the user confirms.
3. Optionally prune DONE rows older than a configurable age at worker start.

Done when the Tasks view's request size does not grow with the number of finished tasks.

### related tickets

- (RELATED) [064-F2_progress_and_cancel](064-F2_progress_and_cancel.md): polls this list, so do this first
- (RELATED) [040-S6_worker_and_handlers](040-S6_worker_and_handlers.md): edits `task_repository.py` too
