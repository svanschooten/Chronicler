"""Server identity and health, used by a thin client to verify what it is talking to."""

import logging

from chronicler import __version__
from chronicler.core import extras
from chronicler.core.config import Settings, get_settings
from chronicler.core.llm import ModelRegistry
from chronicler.core.models import ServerInfo
from chronicler.core.repositories import ChronicleRepository
from chronicler.core.rpc import service

logger = logging.getLogger(__name__)


@service(expose=["get_server_info", "list_models", "model_error", "ping"])
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
            capabilities=sorted(capabilities_for(self.settings)),
        )

    async def ping(self) -> str:
        return "ok"


EXTRA_CAPABILITIES = {"transcribe": "transcription", "normalize": "normalization"}


def capabilities_for(settings: Settings) -> set[str]:
    """
    What this server can actually do, so a client can grey out the rest.

    A thin client has to ask, not check itself: the extras and the model configuration
    that matter are the server's, not its own. See docs/deployment-and-rpc.md.
    """
    found = {"import", "clean", "export"}
    found.update(
        capability for capability, extra in EXTRA_CAPABILITIES.items() if extras.is_available(extra)
    )
    if settings.llm.is_configured:
        found.add("summarize")
    return found
