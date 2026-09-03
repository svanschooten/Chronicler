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
        self.worker_id = worker_id or str(uuid.uuid4())
        self.handlers: dict[TaskType, Callable[[Task, Callable[[int], Any]], Any]] = {}
        self._running = False
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
        pending_count = len(await self.repository.get_pending())
        for _ in range(pending_count):
            task = await self.repository.claim_next(self.worker_id)
            if task is None:
                return
            await self._execute_task(task)

    async def _execute_task(self, task: Task):
        if task.type not in self.handlers:
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
            return
        await self.event_bus.publish(
            TaskCompletedEvent(
                task_id=task.id,
                task_type=task.type,
                status=task.status,
                chronicle_id=task.chronicle_id,
            )
        )
