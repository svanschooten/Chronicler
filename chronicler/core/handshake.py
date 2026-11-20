"""The thin client's startup check against the server it is configured to use."""

import logging

from chronicler import __version__
from chronicler.core.models import ServerInfo
from chronicler.core.services import SystemService

logger = logging.getLogger(__name__)


class HandshakeError(RuntimeError):
    """A thin client could not establish a usable connection to its server."""


async def perform_handshake(system: SystemService) -> ServerInfo:
    """
    Proves the server answers and runs exactly this client's version, and returns what it
    reported. Exact equality, because the generated RPC surface has no version of its own.
    """
    try:
        info: ServerInfo = await system.get_server_info()
    except Exception as error:
        raise HandshakeError(f"Could not reach the Chronicler server: {error}") from error

    if info.version.strip() != __version__.strip():
        raise HandshakeError(
            f"Chronicler server version {info.version} does not match this client "
            f"({__version__}). Upgrade whichever is older so both run the same version."
        )

    count = "unknown" if info.chronicle_count is None else info.chronicle_count
    logger.info(
        f"Connected to Chronicler server (version {info.version}, chronicles: {count}, "
        f"capabilities: {', '.join(info.capabilities) or 'none reported'})"
    )
    return info
