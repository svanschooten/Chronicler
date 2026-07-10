import asyncio
import logging
from collections.abc import Callable
from typing import Any

from chronicler.core.models import Task, TaskStatus, TaskType
from chronicler.core.repositories import TaskRepository

logger = logging.getLogger(__name__)


class WorkerManager:
    def __init__(self, repository: TaskRepository):
        self.repository = repository
        self.handlers: dict[TaskType, Callable[[Task, Callable[[int], Any]], Any]] = {}
        self._running = False

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
        pending_tasks = await self.repository.get_pending()

        for task in pending_tasks:
            await self._execute_task(task)

    async def _execute_task(self, task: Task):
        if task.type not in self.handlers:
            logger.warning(f"No handler registered for task type: {task.type}")
            return

        await self.repository.update_status(task.id, TaskStatus.WORKING)

        async def update_progress(progress: int):
            await self.repository.update_progress(task.id, progress)

        try:
            handler = self.handlers[task.type]
            if asyncio.iscoroutinefunction(handler):
                await handler(task, update_progress)
            else:
                handler(task, update_progress)
            await self.repository.update_status(task.id, TaskStatus.DONE)
        except Exception as e:
            logger.exception(f"Error executing task {task.id}")
            await self.repository.update_status(task.id, TaskStatus.FAILED, error=str(e))


async def perform_test_task(task: Task, update_progress: Callable[[int], Any]):
    """A test worker that waits, updates progress, waits again, and finishes."""
    await asyncio.sleep(1)
    await update_progress(50)
    await asyncio.sleep(1)
    await update_progress(100)
