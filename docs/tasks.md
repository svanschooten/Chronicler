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

`claim_next()` selects the first due `PENDING` task, by priority and then age, and moves
it to `WORKING` in the same session. It is not a compare-and-swap: only one process can
open a workspace and one coroutine runs its worker, so nothing else claims at the same
time.

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
build that on; this class does not solve that, it just avoids closing the door on it. The
design for that push is in [live-updates.md](live-updates.md).

The event bus is optional. Only the desktop app passes one; `None` is a legitimate
default in server mode and in tests.

## Task columns that are not what you would guess

`claimed_at` and `updated_at` already serve as "started" and "completed" — no separate
columns are needed. `updated_at` is bumped on every write to the row, so once a task has
reached a terminal state it is exactly the completion time.
