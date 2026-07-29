from dataclasses import dataclass


@dataclass(frozen=True)
class Chronicle:
    chronicle_id: str
    title: str
    kind: str
    date: str
    duration: str
    speakers: int
    status: str
    preview: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class ProcessingTask:
    task_id: str
    chronicle_title: str
    task_type: str
    provider: str
    progress: str
    state: str


CHRONICLES: tuple[Chronicle, ...] = (
    Chronicle(
        chronicle_id="weekly-product-sync",
        title="Weekly product sync",
        kind="Work meeting",
        date="Today, 10:00",
        duration="48 min",
        speakers=4,
        status="Ready to review",
        preview="Roadmap, customer feedback, and release priorities for the coming sprint.",
        tags=("product", "weekly"),
    ),
    Chronicle(
        chronicle_id="oral-history-alex",
        title="Oral history — Alex Morgan",
        kind="Interview",
        date="Yesterday, 14:30",
        duration="1 h 12 min",
        speakers=2,
        status="Transcribing",
        preview="A conversation about growing up by the coast and the early years of the studio.",
        tags=("interview", "archive"),
    ),
    Chronicle(
        chronicle_id="emberfall-session-14",
        title="Emberfall — session 14",
        kind="D&D campaign",
        date="18 Jul 2026",
        duration="3 h 04 min",
        speakers=5,
        status="Ready to review",
        preview="The party enters the Sunken Archive and makes an uneasy pact with the Archivist.",
        tags=("emberfall", "campaign"),
    ),
    Chronicle(
        chronicle_id="guest-lecture-design",
        title="Guest lecture: Design systems",
        kind="Lecture",
        date="12 Jul 2026",
        duration="56 min",
        speakers=1,
        status="Imported",
        preview="Principles for resilient interface systems, from tokens to governance.",
        tags=("lecture", "design"),
    ),
    Chronicle(
        chronicle_id="emberfall-session-15",
        title="Emberfall — session 15",
        kind="D&D campaign",
        date="23 Jul 2026",
        duration="2 h 15 min",
        speakers=5,
        status="Ready to review",
        preview="The party enters the Sunken Archive and makes an uneasy pact with the Archivist.",
        tags=("emberfall", "campaign"),
    )
)


TASKS: tuple[ProcessingTask, ...] = (
    ProcessingTask("task-1", "Oral history — Alex Morgan", "Transcription", "Faster Whisper", "62%", "In progress"),
    ProcessingTask("task-2", "Guest lecture: Design systems", "Audio normalization", "Local recorder", "Queued", "Waiting"),
    ProcessingTask("task-3", "Weekly product sync", "Transcript cleanup", "Cleanup rules", "Complete", "Finished"),
)


def get_chronicle(chronicle_id: str) -> Chronicle | None:
    return next((item for item in CHRONICLES if item.chronicle_id == chronicle_id), None)
