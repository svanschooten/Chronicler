import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.models import Task, TaskStatus, TaskType
from chronicler.core.sqlite import SQLiteTaskRepository
from chronicler.core.task_events import TaskCompletedEvent, TaskEventBus

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], AsyncSession]

STATUS_WRITE_TIMEOUT = 30.0
"""Seconds a task's final status write keeps retrying while the database is locked."""


class WorkerManager:
    """
    Runs queued tasks. Every group of task-table calls gets a short session of its own, and
    none is held across a handler's run, so a lock timeout fails one step instead of
    poisoning a session the loop keeps using.
    """

    def __init__(
        self,
        sessions: SessionFactory,
        worker_id: str | None = None,
        event_bus: TaskEventBus | None = None,
        status_write_timeout: float = STATUS_WRITE_TIMEOUT,
    ):
        self.sessions = sessions
        self.worker_id = worker_id or str(uuid.uuid4())
        self.handlers: dict[TaskType, Callable[[Task, Callable[[int], Any]], Any]] = {}
        self._running = False
        self.event_bus = event_bus
        self.status_write_timeout = status_write_timeout

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

    @asynccontextmanager
    async def _tasks(self) -> AsyncIterator[SQLiteTaskRepository]:
        async with self.sessions() as session:
            yield SQLiteTaskRepository(session)

    async def process_tasks(self):
        async with self._tasks() as tasks:
            pending_count = len(await tasks.get_pending())
        for _ in range(pending_count):
            async with self._tasks() as tasks:
                task = await tasks.claim_next(self.worker_id)
            if task is None:
                return
            await self._execute_task(task)

    async def _execute_task(self, task: Task):
        if task.type not in self.handlers:
            message = f"No handler registered for task type: {task.type}"
            logger.warning(message)
            await self._record_outcome(
                lambda tasks: tasks.update_status(task.id, TaskStatus.FAILED, error=message)
            )
            await self._publish_completion(task.id)
            return

        logger.info(f"Task {task.id} ({task.type.value}) claimed, starting")

        async def update_progress(progress: int):
            logger.info(f"Task {task.id} ({task.type.value}) progress: {progress}%")
            try:
                async with self._tasks() as tasks:
                    await tasks.update_progress(task.id, progress)
            except OperationalError:
                logger.warning(f"Task {task.id}: could not record progress {progress}%")

        try:
            handler = self.handlers[task.type]
            if asyncio.iscoroutinefunction(handler):
                await handler(task, update_progress)
            else:
                handler(task, update_progress)
        except Exception as e:
            logger.exception(f"Task {task.id} ({task.type.value}) failed")
            error = str(e)
            await self._record_outcome(lambda tasks: tasks.mark_failed_or_retry(task.id, error))
        else:
            await self._record_outcome(lambda tasks: tasks.update_status(task.id, TaskStatus.DONE))
            logger.info(f"Task {task.id} ({task.type.value}) completed")
        await self._publish_completion(task.id)

    async def _record_outcome(
        self, write: Callable[[SQLiteTaskRepository], Awaitable[None]]
    ) -> None:
        """
        Writes a task's final status, retrying while the database is locked, so a lock at
        the wrong moment does not throw away a finished result.
        """
        deadline = time.monotonic() + self.status_write_timeout
        delay = 0.1
        while True:
            try:
                async with self._tasks() as tasks:
                    await write(tasks)
                return
            except OperationalError:
                if time.monotonic() + delay > deadline:
                    raise
                logger.warning(f"Database busy, retrying a task status write in {delay:.1f}s")
                await asyncio.sleep(delay)
                delay = min(delay * 2, 2.0)

    async def _publish_completion(self, task_id: uuid.UUID) -> None:
        if not self.event_bus:
            return
        async with self._tasks() as tasks:
            task = await tasks.get_by_id(task_id)
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
