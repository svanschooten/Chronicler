"""Building service sets for tests that do not need a workspace."""

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock

from chronicler.core.services.services import Services


def serving(*instances: Any) -> Callable[[], Any]:
    """
    The `new_services` an RpcServer takes, for a test that serves a few plain service
    objects: a set that answers `of(cls)` with whichever instance is one.
    """

    class _Set:
        def of(self, service_class: type) -> Any:
            for instance in instances:
                if isinstance(instance, service_class):
                    return instance
            raise LookupError(service_class.__name__)

        async def close(self) -> None:
            return None

    return _Set


def fake_services(**services: Any) -> Services:
    """A `Services` of mocks, for a view test. Name a service to give it a specific double."""
    return Services(
        chronicles=services.get("chronicles", AsyncMock()),
        tasks=services.get("tasks", AsyncMock()),
        transcripts=services.get("transcripts", AsyncMock()),
        system=services.get("system", AsyncMock()),
        close=AsyncMock(),
    )
