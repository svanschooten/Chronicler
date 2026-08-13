import asyncio
import logging
import uuid
from collections.abc import Callable
from typing import Any

from chronicler.core.models import Task, TaskStatus, TaskType
from chronicler.core.repositories import TaskRepository
from chronicler.core.task_events import TaskCompletedEvent, TaskEventBus

logger = logging.getLogger(__name__)


class WorkerManager:
    def __init__(
        self,
        repository: TaskRepository,
        worker_id: str | None = None,
        event_bus: TaskEventBus | None = None,
    ):
        self.repository = repository
        # Identifies this WorkerManager instance for claim_next()'s claimed_by column
        # - useful when more than one process (desktop + server) points at the same
        # workspace, and for any future stale-claim recovery.
        self.worker_id = worker_id or str(uuid.uuid4())
        self.handlers: dict[TaskType, Callable[[Task, Callable[[int], Any]], Any]] = {}
        self._running = False
        # Optional: only the desktop app passes one today (see DesktopApp), so it can
        # refresh whatever view is open when a task it started finishes. None is a
        # legitimate default everywhere else (server mode, tests) - see task_events.py.
        self.event_bus = event_bus

    def register_handler(
        self, task_type: TaskType, handler: Callable[[Task, Callable[[int], Any]], Any]
    ):
        self.handlers[task_type] = handler

    async def run_forever(self, interval: float = 1.0):
        self._running = True
        logger.info("Worker manager started")
        while self._running:
            try:
                await self.process_tasks()
            except Exception:
                logger.exception("Error in worker manager loop")
            await asyncio.sleep(interval)

    def stop(self):
        self._running = False
        logger.info("Worker manager stopped")

    async def process_tasks(self):
        # Bounded to what was pending *before* this cycle started: a task that
        # mark_failed_or_retry() puts back to PENDING mid-cycle (see _execute_task)
        # is immediately re-claimable, and an unbounded claim loop would burn through
        # all of a task's retries in one instant burst instead of spreading them
        # across poll cycles - which defeats the point of retrying at all, since an
        # instant re-attempt gives a transient failure no time to clear.
        pending_count = len(await self.repository.get_pending())
        for _ in range(pending_count):
            task = await self.repository.claim_next(self.worker_id)
            if task is None:
                return
            await self._execute_task(task)

    async def _execute_task(self, task: Task):
        if task.type not in self.handlers:
            # claim_next() already moved this task to WORKING - there's no handler
            # that will ever appear for it, so retrying wouldn't help. Fail it
            # outright rather than leaving it stuck in WORKING or busy-looping it
            # through repeated claim/no-handler/reclaim cycles.
            logger.warning(f"No handler registered for task type: {task.type}")
            await self.repository.update_status(
                task.id,
                TaskStatus.FAILED,
                error=f"No handler registered for task type: {task.type}",
            )
            await self._publish_completion(task.id)
            return

        logger.info(f"Task {task.id} ({task.type.value}) claimed, starting")

        async def update_progress(progress: int):
            logger.info(f"Task {task.id} ({task.type.value}) progress: {progress}%")
            await self.repository.update_progress(task.id, progress)

        try:
            handler = self.handlers[task.type]
            if asyncio.iscoroutinefunction(handler):
                await handler(task, update_progress)
            else:
                handler(task, update_progress)
            await self.repository.update_status(task.id, TaskStatus.DONE)
            logger.info(f"Task {task.id} ({task.type.value}) completed")
            await self._publish_completion(task.id)
        except Exception as e:
            logger.exception(f"Task {task.id} ({task.type.value}) failed")
            await self.repository.mark_failed_or_retry(task.id, str(e))
            await self._publish_completion(task.id)

    async def _publish_completion(self, task_id: uuid.UUID) -> None:
        if not self.event_bus:
            return
        task = await self.repository.get_by_id(task_id)
        if task is None or task.status == TaskStatus.PENDING:
            # mark_failed_or_retry() put it back to PENDING - retries remain, so
            # this isn't "completed" from a listener's point of view yet.
            return
        await self.event_bus.publish(
            TaskCompletedEvent(
                task_id=task.id,
                task_type=task.type,
                status=task.status,
                chronicle_id=task.chronicle_id,
            )
        )


async def perform_test_task(task: Task, update_progress: Callable[[int], Any]):
    """A test worker that waits, updates progress, waits again, and finishes."""
    await asyncio.sleep(1)
    await update_progress(50)
    await asyncio.sleep(1)
    await update_progress(100)
