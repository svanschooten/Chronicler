# Tasks and the worker loop

`chronicler/core/workers.py`, `chronicler/core/worker_wiring.py`,
`chronicler/core/sqlite/task_repository.py`, `chronicler/core/task_events.py`

Long-running operations are persistent rows, not in-memory jobs. They belong to a
Chronicle, survive restarts, and carry a type plus a JSON payload.

## Lifecycle

```
PENDING ──claim_next()──> WORKING ──success──> DONE
   ^  ^                      │
   │  │                      └──failure or interruption──> attempts exhausted? ──> FAILED
   │  └──────────────────────────────────────────────────────────── no ──┘
   └──── worker stopped, no attempt used ──── WORKING
```

An interruption is a task found `WORKING` when the worker starts; see
[Interrupted tasks](#interrupted-tasks).

## Progress and cancelling

A transcription reports progress as it goes. faster-whisper yields segments lazily, so the
transcriber calls `on_progress(fraction)` with `segment.end / info.duration` after each one,
from its own thread. The handler hands each whole-percent step to the event loop with
`run_coroutine_threadsafe` and maps it onto 30-70% of the task's bar. The Tasks view
re-reads the list every 2 seconds while anything is queued or running, through the service,
so a thin client sees it move too.

`TaskService.cancel_task` sets the row to `CANCELLED`. A PENDING task is simply never
claimed. A WORKING one is stopped only for the types in `CANCELLABLE_WHILE_WORKING`
(transcription): the worker polls the row every second (`CANCEL_POLL_SECONDS`) and sets a
`threading.Event`, which the transcriber checks between segments through the context
variable in `chronicler/core/cancellation.py`. The task then ends within a segment, writes
no lines, and marks its source failed with "Cancelled". The row is the only channel, so a
cancel from another process works the same way.

A cancelled task is not a failure. `mark_failed_or_retry` leaves a `CANCELLED` row alone, so
the error that stopping it caused does not put it back in the queue, and recovery only
looks at WORKING rows. *Run again* works on it like on any finished task. Other types are
short, so cancelling one that is already running is refused instead of relabelling work
that carries on.

## Listing and clearing finished tasks

`TaskService.list_tasks(include_finished=False)` returns only PENDING and WORKING tasks,
newest first, so the Tasks view's request does not grow with the history. With
`include_finished` the list is capped at `FINISHED_LIST_LIMIT` (200) newest tasks.
`clear_finished_tasks(include_failed=False)` deletes DONE tasks, and FAILED ones too when
the user chooses to: a failed task is the only record of why it failed. Nothing prunes
automatically; deleting a chronicle still removes its tasks.

## Atomic claiming

`claim_next()` is a `SELECT` of candidates followed by a conditional `UPDATE` that only
succeeds if the row is still `PENDING`. If `rowcount == 0`, another worker claimed that
candidate in between, so the next candidate is tried rather than returning `None`
outright — there may still be unclaimed work.

`MAX_CLAIM_CANDIDATES` bounds how many candidates one call considers before giving up
and waiting for the next poll cycle. It guards against pathologically unlucky
contention without looping forever; in practice a single caller almost always claims
its first candidate.

## Retry backoff

`mark_failed_or_retry()` puts a task back to `PENDING` with a `not_before` time: 30 seconds
after the first failure and 5 minutes after the second (`RETRY_DELAYS`; a later retry
waits the last delay). `claim_next()` skips rows that are not due yet, so a transient
failure such as a restarting gateway has time to clear, and `process_tasks` can simply run
until nothing is due. `retry_task` and `update_status(PENDING)` clear `not_before`, so a
manual retry runs at once. The Tasks view shows the next attempt time.

`TaskService` sets `max_attempts` per task type (`MAX_ATTEMPTS`): a transcription is not
retried automatically, because a late failure would repeat hours of work and a manual
retry exists. Every other type keeps 3.

## Returning a task to the queue

Both `mark_failed_or_retry()` and `update_status(PENDING)` clear `claimed_by`,
`claimed_at` and `progress` (`update_status` also clears `error` and `not_before`). From the queue's point of view the task has not
been attempted, so the previous run's state is stale. Leaving `claimed_by`/`claimed_at`
behind made the Tasks view keep showing the *previous* run's start time until something
claimed it again.

`TaskService.retry_task` deliberately does **not** reset `attempts`. One click buys
exactly one attempt: the automatic retry budget is already spent by the time a task
reaches `FAILED`, and refilling it would make a deterministically failing task (a bad
regex, a missing file) fail three more times per click instead of once.

## Interrupted tasks

A task can be left `WORKING` with nothing running it: the process crashed or was killed,
or its final status write was still locked after `STATUS_WRITE_TIMEOUT`. Only one
process can open a workspace (see [storage.md](storage.md#one-process-per-workspace)),
so any `WORKING` row the worker finds when it starts is one of these.

`run_forever` first calls `recover_interrupted()`, which puts each of them back to
`PENDING` with "Interrupted before finishing" as its error. Nothing is claimed until that
has worked once; a task claimed earlier would look interrupted to it. If it fails, for
example on a locked database, the next poll cycle tries again.

Each recovery costs an attempt, and a task with none left is `FAILED` instead. A task
that takes the process down every time it runs would otherwise run on every start,
forever. A task recovery fails publishes a `TaskCompletedEvent`, like any other failure.

Its handler never saw that failure, so the cleanup a handler does on its own failure path
never ran. `register_cleanup` gives a task type a hook for that case. TRANSCRIBE and
NORMALIZE use it to mark their audio source `FAILED` where it still says `RUNNING`, or
the Sources panel would show the track as transcribing for good. A source already past
`RUNNING` is left alone: the crash came after its work was saved.

Stopping the worker is different. Closing the desktop app or stopping the server cancels
the running task, and `_execute_task` catches the `CancelledError`, returns the task to
`PENDING` without using an attempt, and re-raises. The task did nothing wrong. That write
is tried once, so a locked database holds up shutdown for at most its busy timeout (5 s);
if it fails, the task is still `WORKING` and the next start's recovery picks it up, at the
cost of an attempt. The source of a stopped transcription keeps saying `RUNNING` until the
task runs again.

A stop can also land after the handler finished, while `_record_outcome` is waiting out a
lock to write `DONE` or the failure. The work is done by then, so instead of giving up it
makes one last direct try at that write before stopping. Only if that fails too does the
task stay `WORKING` and run again after the next start: harmless for an import or a
transcription, which replace their lines, but a summary pays for its model call twice.

Cancelling does not stop work running in a thread. A transcription is
`asyncio.to_thread`, so Whisper carries on in the background and its result is thrown
away, and closing the app waits for the interpreter to finish that thread. Real cancel is
[064-F2](../tickets/064-F2_progress_and_cancel.md).

Recovery commits every row first, then runs each failed task's cleanup and publishes its
event. One task's cleanup or event failing is logged and does not stop the next one's: a
second recovery would find nothing left `WORKING` to retry them with.

The Tasks view does not offer retry on `WORKING`. With recovery in place, a `WORKING` row
really is running, and retrying it would run it twice.

## No handler registered

`claim_next()` has already moved the task to `WORKING` by the time the missing handler
is noticed. There is no handler that will ever appear for it, so retrying would not
help — it is failed outright, rather than left stuck in `WORKING` or busy-looped
through repeated claim/no-handler/reclaim cycles.

## Worker wiring

`build_worker_manager` is the one place that maps `TaskType` to handler methods. Both
entry points that run tasks — the desktop app in full-stack mode and the server — need
identical wiring, and a handler registered in only one of them is a task type that
silently never runs in the other.

`worker_id` identifies a `WorkerManager` instance for the `claimed_by` column, for
logs and debugging. Only one process can open a workspace at a time (see
[storage.md](storage.md#one-process-per-workspace)), so it never has to tell two live
workers apart.

## Task events

`TaskEventBus` is in-process publish/subscribe, so a UI sharing the event loop with the
`WorkerManager` — desktop full-stack mode — can refresh live instead of only on the next
manual navigation.

`TaskCompletedEvent` is published once a task reaches a **terminal** state: `DONE`, or
`FAILED` with no retries left. A retry that returns a task to `PENDING` publishes
nothing; from a listener's point of view the task is not completed yet.

A broken listener must not stop other listeners from hearing the event, and must never
take down the worker loop that published it, so `publish` swallows and logs listener
exceptions.

It is deliberately a callback list rather than a message queue or external broker —
today's only real subscriber is the desktop UI in the same process. The shape is
transport-agnostic on purpose though: a future websocket or SSE-backed bus for
thin-client and web could implement the same interface and be handed to `WorkerManager`
unchanged. Today's RPC is request/response only and has no server-push mechanism to
build that on; this class does not solve that, it just avoids closing the door on it.

The event bus is optional. Only the desktop app passes one; `None` is a legitimate
default in server mode and in tests.

## Task columns that are not what you would guess

`claimed_at` and `updated_at` already serve as "started" and "completed" — no separate
columns are needed. `updated_at` is bumped on every write to the row, so once a task has
reached a terminal state it is exactly the completion time.
