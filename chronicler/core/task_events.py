import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from chronicler.core.models import TaskStatus, TaskType

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TaskCompletedEvent:
    """Published once a task reaches a terminal state - DONE, or FAILED with no retries left."""

    task_id: UUID
    task_type: TaskType
    status: TaskStatus
    chronicle_id: UUID | None


TaskEventListener = Callable[[TaskCompletedEvent], "Awaitable[None] | None"]


class TaskEventBus:
    """
    In-process publish/subscribe for task completion, so a UI sharing the same event loop as
    the WorkerManager (desktop full-stack mode) can refresh live instead of only on the next
    manual navigation/refresh click.
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
        for listener in list(self._listeners):
            try:
                result = listener(event)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.exception("Error in task event listener")
