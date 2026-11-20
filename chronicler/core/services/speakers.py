"""Helpers the services that name speakers share."""

import logging

from chronicler.core.sqlite import SQLiteKnownSpeakerRepository

logger = logging.getLogger(__name__)


async def remember_speaker(known_speakers: SQLiteKnownSpeakerRepository | None, name: str) -> None:
    """Adds a name to the workspace-wide registry, ignoring a registry-side failure."""
    if known_speakers is None:
        return
    try:
        await known_speakers.register(name)
    except Exception:
        logger.warning("Could not record speaker %r in the workspace registry", name)
