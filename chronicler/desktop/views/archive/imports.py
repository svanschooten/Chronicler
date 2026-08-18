"""Chronicle import orchestration - the business half of ArchiveView's file picker.

Deliberately Flet-free: picking a file and reporting the outcome are the view's job,
but deciding what an "import audio" or "import transcript" actually *does* to the
workspace is not. Keeping it here means it can be tested without a page attached,
and the view is left with layout plus event plumbing.
"""

import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from chronicler.core.services.chronicle_service import ChronicleService
from chronicler.core.services.task_service import TaskService
from chronicler.core.services.transcript_service import TranscriptService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TranscriptImportOptions:
    """How to parse a transcript file being imported - gathered from the import
    dialog's fields. `regex` of None falls back to DefaultImporter server-side."""

    regex: str | None = None
    speaker_group: int = 1
    text_group: int = 2
    timestamp_group: int | None = None


#: Resolves to "overwrite", "append" or "cancel". Injected rather than called
#: directly so the coordinator stays free of Flet - the view supplies one backed by
#: a real modal, tests supply a plain coroutine.
AskOverwriteOrAppend = Callable[[], Awaitable[str]]


class ImportCoordinator:
    def __init__(
        self,
        chronicle_service: ChronicleService,
        task_service: TaskService,
        transcript_service: TranscriptService,
        stage_file: Callable[[str], Awaitable[str]],
    ):
        self.chronicle_service = chronicle_service
        self.task_service = task_service
        self.transcript_service = transcript_service
        # Picked files can be anywhere on disk (e.g. ~/Downloads); handle_import
        # requires file_path be inside the workspace's imports directory. stage_file
        # copies (local mode) or uploads (thin client mode) the picked file there
        # first and returns the path actually safe to queue.
        self.stage_file = stage_file

    async def import_audio(self, chronicle_id: UUID | None, file_path: str) -> str:
        """Stores an audio file as one of a chronicle's sources, creating the
        chronicle first if `chronicle_id` is None (the header menu's case - a card's
        menu always carries an id). Queues no transcription: importing a source and
        transcribing it are separate actions, so tracks can be gathered first and
        transcribed - with a speaker assigned - later, from the transcript view's
        Sources panel.
        """
        # The original name is what the user recognizes; only the staged path is what
        # is safe to hand onwards.
        original_name = os.path.basename(file_path)
        staged_path = await self.stage_file(file_path)

        if chronicle_id is not None:
            await self.chronicle_service.add_audio_source(chronicle_id, staged_path, original_name)
            return f"Added audio source '{original_name}'"

        title = original_name.rsplit(".", 1)[0]
        chronicle = await self.chronicle_service.create_chronicle(title)
        await self.chronicle_service.add_audio_source(chronicle.id, staged_path, original_name)
        return f"Created '{title}' and added audio source"

    async def import_transcript(
        self,
        chronicle_id: UUID | None,
        file_path: str,
        options: TranscriptImportOptions,
        ask_overwrite_or_append: AskOverwriteOrAppend,
    ) -> str | None:
        """Queues a transcript import task, creating the chronicle first if
        `chronicle_id` is None. Returns None if the user cancelled at the
        overwrite/append prompt - which is only reached when the chronicle already
        has a transcript that a plain import would silently destroy.
        """
        original_name = os.path.basename(file_path)
        staged_path = await self.stage_file(file_path)

        if chronicle_id is None:
            title = original_name.rsplit(".", 1)[0]
            chronicle = await self.chronicle_service.create_chronicle(title)
            await self._queue_import(chronicle.id, staged_path, options, append=False)
            return f"Created '{title}' and queued transcript import"

        append = False
        if await self.transcript_service.get_transcript(chronicle_id):
            choice = await ask_overwrite_or_append()
            if choice == "cancel":
                return None
            append = choice == "append"

        await self._queue_import(chronicle_id, staged_path, options, append=append)
        return "Transcript append task queued" if append else "Transcript import task queued"

    async def _queue_import(
        self,
        chronicle_id: UUID,
        staged_path: str,
        options: TranscriptImportOptions,
        append: bool,
    ) -> None:
        await self.task_service.queue_import(
            chronicle_id,
            staged_path,
            regex=options.regex,
            speaker_group=options.speaker_group,
            text_group=options.text_group,
            timestamp_group=options.timestamp_group,
            append=append,
        )

    async def link_chronicle(self, file_path: str) -> str:
        """Registers an existing project.db that lives outside the workspace. The
        file is *not* staged or copied - a linked chronicle deliberately keeps its
        data where the user put it (see ChronicleService.delete_chronicle).
        """
        # <somewhere>/<chronicle name>/project.db is the usual shape, so the parent
        # directory is the best available title - unless that parent is the generic
        # "chronicles" container, in which case fall back to the file's own name.
        title = os.path.basename(os.path.dirname(file_path))
        if title == "chronicles" or not title:
            title = os.path.basename(file_path).rsplit(".", 1)[0]

        await self.chronicle_service.create_chronicle(title, project_path=file_path)
        return f"Linked external chronicle '{title}'"
