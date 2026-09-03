# Tasks and the worker loop

`chronicler/core/workers.py`, `chronicler/core/worker_wiring.py`,
`chronicler/core/sqlite/task_repository.py`, `chronicler/core/task_events.py`

Long-running operations are persistent rows, not in-memory jobs. They belong to a
Chronicle, survive restarts, and carry a type plus a JSON payload.

## Lifecycle

```
PENDING ──claim_next()──> WORKING ──success──> DONE
   ^                         │
   │                         └──failure──> attempts exhausted? ──> FAILED
   └─────────────────────────────────────── no ──┘
```

## Atomic claiming

`claim_next()` is a `SELECT` of candidates followed by a conditional `UPDATE` that only
succeeds if the row is still `PENDING`. If `rowcount == 0`, another worker claimed that
candidate in between, so the next candidate is tried rather than returning `None`
outright — there may still be unclaimed work.

`MAX_CLAIM_CANDIDATES` bounds how many candidates one call considers before giving up
and waiting for the next poll cycle. It guards against pathologically unlucky
contention without looping forever; in practice a single caller almost always claims
its first candidate.

## Why `process_tasks` is bounded

The loop is bounded to what was pending *before* the cycle started.

A task that `mark_failed_or_retry()` puts back to `PENDING` mid-cycle is immediately
re-claimable, and an unbounded claim loop would burn through all of a task's retries in
one instant burst instead of spreading them across poll cycles. That defeats the point
of retrying at all — an instant re-attempt gives a transient failure no time to clear.

## Returning a task to the queue

Both `mark_failed_or_retry()` and `update_status(PENDING)` clear `claimed_by`,
`claimed_at`, `error` and `progress`. From the queue's point of view the task has not
been attempted, so the previous run's state is stale. Leaving `claimed_by`/`claimed_at`
behind made the Tasks view keep showing the *previous* run's start time until something
claimed it again.

`TaskService.retry_task` deliberately does **not** reset `attempts`. One click buys
exactly one attempt: the automatic retry budget is already spent by the time a task
reaches `FAILED`, and refilling it would make a deterministically failing task (a bad
regex, a missing file) fail three more times per click instead of once.

## No handler registered

`claim_next()` has already moved the task to `WORKING` by the time the missing handler
is noticed. There is no handler that will ever appear for it, so retrying would not
help — it is failed outright, rather than left stuck in `WORKING` or busy-looped
through repeated claim/no-handler/reclaim cycles.

## Worker wiring

`build_worker_runtime` is the one place that maps `TaskType` to handler methods. Both
entry points that run tasks — the desktop app in full-stack mode and the server — need
identical wiring, and a handler registered in only one of them is a task type that
silently never runs in the other.

`worker_id` identifies a `WorkerManager` instance for the `claimed_by` column. It
matters when more than one process (desktop plus server) points at the same workspace,
and for any future stale-claim recovery.

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
