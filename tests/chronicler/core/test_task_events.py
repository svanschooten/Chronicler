from uuid import uuid4

import pytest

from chronicler.core.models import TaskStatus, TaskType
from chronicler.core.task_events import TaskCompletedEvent, TaskEventBus


def _event(status=TaskStatus.DONE) -> TaskCompletedEvent:
    return TaskCompletedEvent(
        task_id=uuid4(), task_type=TaskType.TRANSCRIBE, status=status, chronicle_id=uuid4()
    )


@pytest.mark.asyncio
async def test_publish_calls_subscribed_async_listener():
    bus = TaskEventBus()
    received = []

    async def listener(event):
        received.append(event)

    bus.subscribe(listener)
    event = _event()
    await bus.publish(event)

    assert received == [event]


@pytest.mark.asyncio
async def test_publish_calls_subscribed_sync_listener():
    bus = TaskEventBus()
    received = []

    def listener(event):
        received.append(event)

    bus.subscribe(listener)
    await bus.publish(_event())

    assert len(received) == 1


@pytest.mark.asyncio
async def test_unsubscribe_stops_further_delivery():
    bus = TaskEventBus()
    received = []
    unsubscribe = bus.subscribe(lambda event: received.append(event))

    unsubscribe()
    await bus.publish(_event())

    assert received == []


@pytest.mark.asyncio
async def test_a_broken_listener_does_not_stop_other_listeners():
    bus = TaskEventBus()
    received = []

    def broken_listener(event):
        raise RuntimeError("boom")

    bus.subscribe(broken_listener)
    bus.subscribe(lambda event: received.append(event))

    await bus.publish(_event())  # must not raise

    assert len(received) == 1


@pytest.mark.asyncio
async def test_publish_with_no_subscribers_does_not_raise():
    bus = TaskEventBus()
    await bus.publish(_event())
