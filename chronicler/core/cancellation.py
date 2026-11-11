"""
How a running task finds out it was cancelled.

The worker puts a `threading.Event` in `cancel_event` while a task runs, and sets it when the
task's row becomes CANCELLED. A context variable rather than an argument, because a handler
hands its work to `asyncio.to_thread`, which copies the context: the thread sees the same
event without every handler and every worker function growing a parameter.
"""

import threading
from contextvars import ContextVar

cancel_event: ContextVar[threading.Event | None] = ContextVar("cancel_event", default=None)


class TaskCancelledError(Exception):
    """The running task was cancelled. Not a failure: the task is not retried."""


def raise_if_cancelled() -> None:
    event = cancel_event.get()
    if event is not None and event.is_set():
        raise TaskCancelledError("The task was cancelled")
