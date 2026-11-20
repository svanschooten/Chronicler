"""The four services, built together for one unit of work, in either deployment mode."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

import httpx

from chronicler.core.config import Settings
from chronicler.core.database_manager import DatabaseManager
from chronicler.core.remote import RemoteServiceProxy
from chronicler.core.services.chronicle_service import ChronicleService, LinkPolicy
from chronicler.core.services.export_service import ExportService
from chronicler.core.services.source_service import SourceService
from chronicler.core.services.summary_service import SummaryService
from chronicler.core.services.system_service import SystemService
from chronicler.core.services.task_service import TaskService
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.core.sqlite import (
    SQLiteChronicleRepository,
    SQLiteKnownSpeakerRepository,
    SQLiteTaskRepository,
)

T = TypeVar("T")


@dataclass
class Services:
    """
    One set of services. A local set shares one archive session, so each request or view
    builds its own and calls `close` when done. A remote set holds proxies in the same
    fields, so what uses it does not know which it has.
    """

    chronicles: ChronicleService
    tasks: TaskService
    transcripts: TranscriptService
    system: SystemService
    exports: ExportService
    sources: SourceService
    summaries: SummaryService
    close: Callable[[], Awaitable[None]]

    def of(self, service_class: type[T]) -> T:
        """
        The service of that class, for the RPC server, which is given classes to serve.
        Local sets only: a remote set holds proxies, which are not instances of the class.
        """
        for service in (
            self.chronicles,
            self.tasks,
            self.transcripts,
            self.system,
            self.exports,
            self.sources,
            self.summaries,
        ):
            if isinstance(service, service_class):
                return service
        raise LookupError(f"No {service_class.__name__} in these services")


def local_services(
    db_manager: DatabaseManager, settings: Settings, link_policy: LinkPolicy | None = None
) -> Services:
    """The services over a workspace, on one new archive session that `close` returns."""
    session = db_manager.get_archive_session()
    chronicle_repository = SQLiteChronicleRepository(session)
    known_speakers = SQLiteKnownSpeakerRepository(session)
    transcripts = TranscriptService(db_manager, chronicle_repository, known_speakers)
    sources = SourceService(db_manager, known_speakers)
    return Services(
        chronicles=ChronicleService(chronicle_repository, db_manager, transcripts, link_policy),
        tasks=TaskService(SQLiteTaskRepository(session)),
        transcripts=transcripts,
        system=SystemService(chronicle_repository, settings),
        exports=ExportService(db_manager, chronicle_repository, transcripts, sources),
        sources=sources,
        summaries=SummaryService(db_manager),
        close=session.close,
    )


def remote_services(url: str, api_key: str | None, client: httpx.AsyncClient) -> Services:
    """Proxies for a server's services. Nothing is held open here, so `close` does nothing."""

    async def close() -> None:
        return None

    return Services(
        chronicles=RemoteServiceProxy(url, ChronicleService, client, api_key),  # type: ignore[arg-type]
        tasks=RemoteServiceProxy(url, TaskService, client, api_key),  # type: ignore[arg-type]
        transcripts=RemoteServiceProxy(url, TranscriptService, client, api_key),  # type: ignore[arg-type]
        system=RemoteServiceProxy(url, SystemService, client, api_key),  # type: ignore[arg-type]
        exports=RemoteServiceProxy(url, ExportService, client, api_key),  # type: ignore[arg-type]
        sources=RemoteServiceProxy(url, SourceService, client, api_key),  # type: ignore[arg-type]
        summaries=RemoteServiceProxy(url, SummaryService, client, api_key),  # type: ignore[arg-type]
        close=close,
    )
