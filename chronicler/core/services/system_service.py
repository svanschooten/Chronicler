"""Server identity and health, used by a thin client to verify what it is talking to."""

import logging

from chronicler import __version__
from chronicler.core.config import Settings, get_settings
from chronicler.core.llm import ModelRegistry
from chronicler.core.models import ServerInfo
from chronicler.core.repositories import ChronicleRepository
from chronicler.core.rpc import service

logger = logging.getLogger(__name__)


@service
class SystemService:
    def __init__(
        self,
        chronicle_repository: ChronicleRepository | None = None,
        settings: Settings | None = None,
    ):
        self.chronicle_repository = chronicle_repository
        self.settings = settings or get_settings()
        self._models = ModelRegistry(self.settings.llm)

    async def list_models(self, refresh: bool = False) -> list[str]:
        """Model ids the configured provider offers, cached between calls."""
        return await self._models.model_ids(refresh=refresh)

    async def model_error(self) -> str | None:
        return self._models.last_error

    async def get_server_info(self) -> ServerInfo:
        chronicle_count = None
        if self.chronicle_repository is not None:
            try:
                chronicle_count = len(await self.chronicle_repository.get_all())
            except Exception:
                logger.warning("Could not count chronicles for server info", exc_info=True)

        return ServerInfo(
            version=__version__,
            chronicle_count=chronicle_count,
            capabilities=sorted(_capabilities()),
        )

    async def ping(self) -> str:
        return "ok"


def _capabilities() -> set[str]:
    """Optional extras this server can actually run, so a client can grey out the rest."""
    found = {"import", "clean", "export"}
    try:
        import faster_whisper  # noqa: F401

        found.add("transcribe")
    except ImportError:
        pass
    return found
