"""Server identity and health, used by a thin client to verify what it is talking to."""

import asyncio
import logging

from chronicler import __version__
from chronicler.core import extras
from chronicler.core.config import Settings, get_settings
from chronicler.core.llm import discover_models
from chronicler.core.models import ModelCheck, ServerInfo
from chronicler.core.repositories import ChronicleRepository
from chronicler.core.rpc import service

logger = logging.getLogger(__name__)


@service(expose=["get_server_info", "list_models", "ping"])
class SystemService:
    def __init__(
        self,
        chronicle_repository: ChronicleRepository | None = None,
        settings: Settings | None = None,
    ):
        self.chronicle_repository = chronicle_repository
        self.settings = settings or get_settings()

    async def list_models(self) -> ModelCheck:
        """The model ids the configured provider offers, and why not if it cannot say."""
        return await discover_models(self.settings.llm)

    async def get_server_info(self) -> ServerInfo:
        chronicle_count = None
        if self.chronicle_repository is not None:
            try:
                chronicle_count = len(await self.chronicle_repository.get_all())
            except Exception:
                logger.warning("Could not count chronicles for server info", exc_info=True)

        # Off the event loop: availability means the module really imports, and the first
        # import of an extra such as faster_whisper takes seconds.
        capabilities = await asyncio.to_thread(capabilities_for, self.settings)
        return ServerInfo(
            version=__version__,
            chronicle_count=chronicle_count,
            capabilities=sorted(capabilities),
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
