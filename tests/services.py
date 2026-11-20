"""Building service sets for tests that do not need a workspace."""

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock

from chronicler.core.services import (
    ExportService,
    SourceService,
    SummaryService,
    TranscriptService,
)
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
        exports=services.get("exports", AsyncMock()),
        sources=services.get("sources", AsyncMock()),
        summaries=services.get("summaries", AsyncMock()),
        close=AsyncMock(),
    )


def build_services(db_manager: Any, chronicle_repository: Any, known_speakers: Any = None):
    """
    The transcript-side services over one repository, built as `local_services` builds
    them but on a session the test already holds. A namespace of `transcripts`, `sources`,
    `summaries` and `exports`.
    """
    from types import SimpleNamespace

    transcripts = TranscriptService(db_manager, chronicle_repository, known_speakers)
    sources = SourceService(db_manager, known_speakers)
    return SimpleNamespace(
        transcripts=transcripts,
        sources=sources,
        summaries=SummaryService(db_manager),
        exports=ExportService(db_manager, chronicle_repository, transcripts, sources),
    )
