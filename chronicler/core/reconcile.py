"""Making a chronicle's archive row agree with the transcript its project database holds."""

import logging
from uuid import UUID

from chronicler.core.formatting import format_duration, looks_synthetic
from chronicler.core.models import Chronicle, TranscriptLine
from chronicler.core.sqlite import SQLiteChronicleRepository

logger = logging.getLogger(__name__)

SUMMARIZABLE = ("Imported", "Transcribed", "Cleaned")
"""The statuses a first summary moves on to "Summarized". Later ones stay as they are."""


async def reconcile(
    chronicles: SQLiteChronicleRepository,
    chronicle_id: UUID,
    lines: list[TranscriptLine],
    summaries: int = 0,
    timings: bool = False,
) -> Chronicle | None:
    """
    The one place that derives speaker count, duration, tags and status from a transcript.
    Every task that rewrites one, and every action that reads a project database back in
    (a link, a restore), calls this with the lines now in it. Returns None for a chronicle
    with no row, which a task that raced a delete leaves nothing to update.

    The speaker count and the tags always follow the lines. Duration and the move from
    "Imported" to "Transcribed" follow them only with `timings`: a transcription, or a
    project database read back in, says how long the recording is. An import or a clean
    does not, so a duration typed by hand survives it and an imported text stays
    "Imported".
    """
    chronicle = await chronicles.get_by_id(chronicle_id)
    if chronicle is None:
        return None

    if lines:
        await chronicles.add_tag(chronicle_id, "Transcript")
    if summaries:
        await chronicles.add_tag(chronicle_id, "Summarized")

    chronicle.speakers_count = len({line.speaker_name for line in lines})
    if timings and lines and not looks_synthetic(lines):
        chronicle.duration = format_duration(max(line.end_time for line in lines))
    if timings and lines and chronicle.status == "Imported":
        chronicle.status = "Transcribed"
    if summaries and chronicle.status in SUMMARIZABLE:
        chronicle.status = "Summarized"

    logger.info(f"Reconciled chronicle {chronicle_id}: {chronicle.speakers_count} speakers")
    return await chronicles.update(chronicle)
