# 040-S6_worker_and_handlers

## Simplify the worker and its handlers

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Low: maintenance cost. Change risk: medium, central code path. |
| reach | Internal. About 100 lines |
| effort | M |
| evidence | read in code |
| touches | `chronicler/core/processing/handlers/`, `chronicler/core/worker_wiring.py`, `chronicler/core/workers.py`, `chronicler/core/sqlite/task_repository.py`, `chronicler/core/services/chronicle_service.py`, `chronicler/core/services/transcript_service.py` |

### description

- `WorkerHandlers` combines handlers by multiple inheritance (`handlers/__init__.py:11`),
  and `TranscribeHandler` inherits from `NormalizeHandler` to reuse a method.
- 5 `if not self.chronicle_repo` guards protect a dependency production always passes.
- Chronicle metadata backfill exists in 5 variants: `backfill_speakers_count`,
  `_backfill_metadata`, `_mark_summarized`, `hydrate_from_project`,
  `refresh_speaker_count`.
- `claim_next` is a SELECT, a loop and a conditional UPDATE, with a constant bounding the
  loop.
- `_execute_task` keeps a branch for sync handlers that no handler uses, through the
  deprecated `asyncio.iscoroutinefunction`.

### proposed fix

1. Build a dict of handler objects in `build_worker_runtime`, and share
   `ensure_normalized` as a plain function.
2. Make the dependency required, and delete the guards.
3. Replace the five backfills with one `reconcile(chronicle_id)`.
4. Replace `claim_next` with one statement. Since 008 only one process can open a
   workspace, and the worker is one coroutine, so nothing else claims concurrently: a
   plain select-then-update would also do, and is simpler to read.
   The atomic form, for reference. This sketch has not been run, needs SQLite 3.35 or
   newer, and predates 022, so it still lacks the `not_before` condition `claim_next`
   has now:

```python
next_id = (
    select(DBTask.id)
    .where(DBTask.status == TaskStatus.PENDING)
    .order_by(DBTask.priority.desc(), DBTask.created_at)
    .limit(1)
    .scalar_subquery()
)
task = await session.scalar(
    update(DBTask)
    .where(DBTask.id == next_id, DBTask.status == TaskStatus.PENDING)
    .values(status=TaskStatus.WORKING, claimed_by=worker_id, claimed_at=datetime.now())
    .returning(DBTask)
)
```

Done when behaviour is unchanged, and the listed constructs are gone.

### related tickets

- (BLOCKER) [007-C2_worker_session_per_step](007-C2_worker_session_per_step.md): changes how the worker gets sessions
- (BLOCKER) [009-C4_task_recovery](009-C4_task_recovery.md): edits the same repository
- (BLOCKER) [022-M6_retry_backoff](022-M6_retry_backoff.md): changes what `claim_next` selects
- (BLOCKER) [010-C5_transcript_line_source_id](010-C5_transcript_line_source_id.md): edits the transcribe handler
- (BLOCKER) [011-H4_clean_confirm_and_snapshot](011-H4_clean_confirm_and_snapshot.md): edits the clean handler
- (BLOCKER) [032-S4_project_db_access](032-S4_project_db_access.md): handlers should use the new helper first
- (BLOCKS) [051-L7_speaker_count_definition](051-L7_speaker_count_definition.md): builds on `reconcile`
- (RELATED) [064-F2_progress_and_cancel](064-F2_progress_and_cancel.md): same handler code. Goes first now, so this rebases on it
- (RELATED) [077-L15_task_history_grows](077-L15_task_history_grows.md): edits `task_repository.py` too
