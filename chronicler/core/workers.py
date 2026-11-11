import asyncio
import logging
import threading
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, TypeVar

from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.cancellation import TaskCancelledError, cancel_event
from chronicler.core.models import Task, TaskStatus, TaskType
from chronicler.core.sqlite import SQLiteTaskRepository
from chronicler.core.task_events import TaskCompletedEvent, TaskEventBus

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], AsyncSession]

STATUS_WRITE_TIMEOUT = 30.0
"""Seconds a task's final status write keeps retrying while the database is locked."""

INTERRUPTED = "Interrupted before finishing"
"""The error recorded on a task found WORKING when the worker starts."""

CANCEL_POLL_SECONDS = 1.0
"""How often a running task's row is checked for a cancel request."""

Cleanup = Callable[[Task], Awaitable[None]]

T = TypeVar("T")


def _is_busy(error: OperationalError) -> bool:
    """Whether SQLite gave up waiting on another connection's lock."""
    message = str(error.orig or error).lower()
    return "locked" in message or "busy" in message


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
        self.cleanups: dict[TaskType, Cleanup] = {}
        self._recovered = False
        self._running = False
        self.event_bus = event_bus
        self.status_write_timeout = status_write_timeout

    def register_handler(
        self, task_type: TaskType, handler: Callable[[Task, Callable[[int], Any]], Any]
    ):
        self.handlers[task_type] = handler

    def register_cleanup(self, task_type: TaskType, cleanup: Cleanup):
        """
        Runs for a task that recovery fails, the one failure its handler never saw, so the
        handler's own failure path did not run either.
        """
        self.cleanups[task_type] = cleanup

    async def run_forever(self, interval: float = 1.0):
        self._running = True
        logger.info("Worker manager started")
        while self._running:
            try:
                # Nothing is claimed until this has worked once: a task this worker claimed
                # would otherwise look interrupted to it.
                if not self._recovered:
                    await self.recover_interrupted()
                    self._recovered = True
                await self.process_tasks()
            except Exception:
                logger.exception("Error in worker manager loop")
            await asyncio.sleep(interval)

    def stop(self):
        self._running = False
        logger.info("Worker manager stopped")

    async def recover_interrupted(self) -> None:
        """
        A task still WORKING when the worker starts was cut off by a crash, or by a status
        write that never got through. Only this process can have the workspace open, so
        none of them is running. Each one costs an attempt, so a task that takes the
        process down every time it runs still ends up FAILED. See docs/tasks.md.
        """
        async with self._tasks() as tasks:
            recovered = await tasks.recover_interrupted(INTERRUPTED)
        for task in recovered:
            outcome = "failed" if task.status == TaskStatus.FAILED else "returned to the queue"
            logger.warning(f"Task {task.id} ({task.type.value}) was interrupted, {outcome}")
            if task.status != TaskStatus.FAILED:
                continue
            # The rows are committed, so a retry would find nothing to recover: one task's
            # failure here must not cost the tasks after it their cleanup.
            cleanup = self.cleanups.get(task.type)
            if cleanup is not None:
                try:
                    await cleanup(task)
                except Exception:
                    logger.exception(f"Cleaning up after interrupted task {task.id} failed")
            try:
                await self._publish_completion(task.id)
            except Exception:
                logger.exception(f"Could not announce that interrupted task {task.id} failed")

    @asynccontextmanager
    async def _tasks(self) -> AsyncIterator[SQLiteTaskRepository]:
        async with self.sessions() as session:
            yield SQLiteTaskRepository(session)

    async def process_tasks(self):
        """
        Runs every task that is due. A failed task waits out its `not_before` before it can
        be claimed again, so this loop cannot spin on it.
        """
        while True:
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

        cancelled = threading.Event()
        token = cancel_event.set(cancelled)
        watcher = asyncio.create_task(self._watch_for_cancel(task, cancelled))
        try:
            handler = self.handlers[task.type]
            if asyncio.iscoroutinefunction(handler):
                await handler(task, update_progress)
            else:
                handler(task, update_progress)
        except asyncio.CancelledError:
            await self._return_to_queue(task)
            raise
        except TaskCancelledError:
            logger.info(f"Task {task.id} ({task.type.value}) cancelled")
        except Exception as e:
            logger.exception(f"Task {task.id} ({task.type.value}) failed")
            error = str(e)
            await self._record_outcome(lambda tasks: tasks.mark_failed_or_retry(task.id, error))
        else:
            await self._record_outcome(lambda tasks: tasks.update_status(task.id, TaskStatus.DONE))
            logger.info(f"Task {task.id} ({task.type.value}) completed")
        finally:
            watcher.cancel()
            cancel_event.reset(token)
        await self._publish_completion(task.id)

    async def _watch_for_cancel(self, task: Task, cancelled: threading.Event) -> None:
        """
        Sets `cancelled` once the task's row says CANCELLED. The row is the one place a
        cancel request from another process, such as a thin client's, can come through.
        """
        while not cancelled.is_set():
            await asyncio.sleep(CANCEL_POLL_SECONDS)
            try:
                async with self._tasks() as tasks:
                    current = await tasks.get_by_id(task.id)
            except OperationalError:
                continue
            if current is not None and current.status == TaskStatus.CANCELLED:
                cancelled.set()

    async def _return_to_queue(self, task: Task) -> None:
        """
        The worker is being stopped. The task did nothing wrong, so it goes back to
        PENDING without using an attempt. One try only, so a locked database holds up
        shutdown for at most its busy timeout; if it fails, recovery at the next start
        picks the task up instead.
        """
        logger.info(f"Task {task.id} ({task.type.value}) stopped, returning it to the queue")
        try:
            async with self._tasks() as tasks:
                await tasks.update_status(task.id, TaskStatus.PENDING)
        except Exception:
            logger.warning(f"Task {task.id}: could not return it to the queue", exc_info=True)

    async def _record_outcome(
        self, write: Callable[[SQLiteTaskRepository], Awaitable[None]]
    ) -> None:
        """
        Writes a task's final status, retrying while the database is locked, so a lock at
        the wrong moment does not throw away a finished result.
        """
        try:
            await self._retry_while_busy(write, "a task status write")
        except asyncio.CancelledError:
            # Stopped while waiting out a lock. The work itself is finished, so one last
            # try is worth making: without it, recovery runs the task again next start.
            await self._last_try(write)
            raise

    async def _retry_while_busy(
        self, operation: Callable[[SQLiteTaskRepository], Awaitable[T]], what: str
    ) -> T:
        """Runs `operation` on a fresh session, retrying while locked, for a bounded time."""
        deadline = time.monotonic() + self.status_write_timeout
        delay = 0.1
        while True:
            try:
                async with self._tasks() as tasks:
                    return await operation(tasks)
            except OperationalError as error:
                # Only a lock clears by waiting; a missing table or a full disk does not.
                if not _is_busy(error) or time.monotonic() + delay > deadline:
                    raise
                logger.warning(f"Database busy, retrying {what} in {delay:.1f}s")
                await asyncio.sleep(delay)
                delay = min(delay * 2, 2.0)

    async def _last_try(self, write: Callable[[SQLiteTaskRepository], Awaitable[None]]) -> None:
        try:
            async with self._tasks() as tasks:
                await write(tasks)
        except Exception:
            logger.warning(
                "Could not record a finished task's outcome before stopping; "
                "it will run again after the next start",
                exc_info=True,
            )

    async def _publish_completion(self, task_id: uuid.UUID) -> None:
        if not self.event_bus:
            return
        try:
            task = await self._retry_while_busy(
                lambda tasks: tasks.get_by_id(task_id), "reading a finished task"
            )
        except OperationalError:
            logger.warning(f"Task {task_id}: could not read it back to announce it", exc_info=True)
            return
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
