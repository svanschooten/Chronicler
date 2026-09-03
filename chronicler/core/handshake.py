"""The thin client's startup check against the server it is configured to use."""

import logging
from dataclasses import dataclass
from typing import Any

from chronicler import __version__
from chronicler.core.models import ServerInfo
from chronicler.core.services import ChronicleService, SystemService

logger = logging.getLogger(__name__)


class HandshakeError(RuntimeError):
    """A thin client could not establish a usable connection to its server."""


class ServerUnreachableError(HandshakeError):
    pass


class VersionMismatchError(HandshakeError):
    pass


@dataclass(frozen=True)
class HandshakeResult:
    server_info: ServerInfo
    version_matches: bool
    chronicle_count: int | None


def versions_compatible(server_version: str, client_version: str) -> bool:
    """Exact equality: the generated RPC surface is not versioned independently."""
    return bool(server_version.strip()) and server_version.strip() == client_version.strip()


async def perform_handshake(
    resolver: Any, require_matching_version: bool = True
) -> HandshakeResult:
    """Verifies the server is reachable and version-compatible, then pulls opening state."""
    system: SystemService = resolver.resolve(SystemService)

    try:
        info = await system.get_server_info()
    except Exception as error:
        raise ServerUnreachableError(f"Could not reach the Chronicler server: {error}") from error

    matches = versions_compatible(info.version, __version__)
    if not matches:
        message = (
            f"Chronicler server version {info.version} does not match this client "
            f"({__version__}). Upgrade whichever is older so both run the same version."
        )
        if require_matching_version:
            raise VersionMismatchError(message)
        logger.warning(message)

    chronicle_count = None
    try:
        chronicles = await resolver.resolve(ChronicleService).list_chronicles()
        chronicle_count = len(chronicles)
    except Exception:
        logger.warning("Connected, but could not list chronicles", exc_info=True)

    logger.info(
        f"Connected to Chronicler server (version {info.version}, "
        f"chronicles: {chronicle_count if chronicle_count is not None else 'unknown'}, "
        f"capabilities: {', '.join(info.capabilities) or 'none reported'})"
    )
    return HandshakeResult(
        server_info=info, version_matches=matches, chronicle_count=chronicle_count
    )
