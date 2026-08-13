import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from chronicler.core.models import TaskStatus, TaskType

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TaskCompletedEvent:
    """Published once a task reaches a terminal state - DONE, or FAILED with no
    retries left. A retry that puts a task back to PENDING does *not* publish one;
    from a listener's point of view the task isn't "completed" yet.
    """

    task_id: UUID
    task_type: TaskType
    status: TaskStatus
    chronicle_id: UUID | None


TaskEventListener = Callable[[TaskCompletedEvent], "Awaitable[None] | None"]


class TaskEventBus:
    """In-process publish/subscribe for task completion, so a UI sharing the same
    event loop as the WorkerManager (desktop full-stack mode) can refresh live
    instead of only on the next manual navigation/refresh click.

    Deliberately just a callback list, not a message queue or external broker -
    today's only real subscriber is the desktop UI in the same process. The shape
    (subscribe/publish over TaskCompletedEvent) is deliberately transport-agnostic
    though: a future websocket/SSE-backed bus for thin-client/web could implement the
    same interface and be handed to WorkerManager the same way, without
    WorkerManager itself changing. Today's RPC (RemoteServiceProxy, request/response
    only) has no server-push mechanism to build that on yet - this class doesn't
    solve that, it just avoids closing the door on it.
    """

    def __init__(self):
        self._listeners: list[TaskEventListener] = []

    def subscribe(self, listener: TaskEventListener) -> Callable[[], None]:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    async def publish(self, event: TaskCompletedEvent) -> None:
        # A broken listener must not stop other listeners from hearing about the
        # event, and must never take down the worker loop that published it.
        for listener in list(self._listeners):
            try:
                result = listener(event)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.exception("Error in task event listener")
