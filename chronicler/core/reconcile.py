"""Making a chronicle's archive row agree with the transcript its project database holds."""

import logging
from uuid import UUID

from chronicler.core.formatting import format_duration, looks_synthetic
from chronicler.core.models import Chronicle, TranscriptLine
from chronicler.core.sqlite import SQLiteChronicleRepository

logger = logging.getLogger(__name__)

SUMMARIZABLE = ("Imported", "Transcribed", "Cleaned")
"""The statuses a first summary moves on to "Summarized". Later ones stay as they are."""


def count_speakers(lines: list[TranscriptLine]) -> int:
    """The speakers with at least one line. A speaker row outlives its lines on purpose."""
    return len({line.speaker_name for line in lines})


async def update_speaker_count(
    chronicles: SQLiteChronicleRepository, chronicle_id: UUID, lines: list[TranscriptLine]
) -> None:
    """
    Only the count, for an edit that cannot change anything else reconcile derives, so a
    duration someone set by hand survives a corrected word.
    """
    chronicle = await chronicles.get_by_id(chronicle_id)
    count = count_speakers(lines)
    if chronicle is not None and chronicle.speakers_count != count:
        chronicle.speakers_count = count
        await chronicles.update(chronicle)


async def reconcile(
    chronicles: SQLiteChronicleRepository,
    chronicle_id: UUID,
    lines: list[TranscriptLine],
    summaries: int = 0,
) -> Chronicle | None:
    """
    The one place that derives speaker count, duration, tags and status from a transcript.
    Every task that rewrites one, and every action that reads a project database back in
    (a link, a restore), calls this with the lines now in it. Returns None for a chronicle
    with no row, which a task that raced a delete leaves nothing to update.
    """
    chronicle = await chronicles.get_by_id(chronicle_id)
    if chronicle is None:
        return None

    if lines:
        await chronicles.add_tag(chronicle_id, "Transcript")
    if summaries:
        await chronicles.add_tag(chronicle_id, "Summarized")

    chronicle.speakers_count = count_speakers(lines)
    if lines and not looks_synthetic(lines):
        chronicle.duration = format_duration(max(line.end_time for line in lines))
    if lines and chronicle.status == "Imported":
        chronicle.status = "Transcribed"
    if summaries and chronicle.status in SUMMARIZABLE:
        chronicle.status = "Summarized"

    logger.info(f"Reconciled chronicle {chronicle_id}: {chronicle.speakers_count} speakers")
    return await chronicles.update(chronicle)
