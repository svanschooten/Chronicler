"""
Every chronicle-level operation, in one place and with no layout.

The archive list and the chronicle view both offer clean, identify speakers, import,
edit and delete. They used to implement them separately, and had already drifted - one
set translated and sharing an error path, the other neither. Layout still differs
between the two; behaviour no longer does. See docs/desktop.md.
"""

import logging
from collections.abc import Awaitable, Callable

import flet as ft

from chronicler.core.models import Chronicle
from chronicler.core.services.chronicle_service import ChronicleService
from chronicler.core.services.task_service import TaskService
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.desktop.dialogs import Choice, ask_choice, confirm
from chronicler.desktop.forms import EditChronicleForm, TranscriptImportForm
from chronicler.desktop.imports import ImportCoordinator
from chronicler.desktop.picking import FilePickerFlow
from chronicler.i18n import t

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = ["mp3", "wav", "m4a", "flac", "ogg"]
TRANSCRIPT_EXTENSIONS = ["txt"]
PROJECT_EXTENSIONS = ["db"]


class ChronicleOperations:
    """
    Each operation returns True when the caller should reload, so a view does not have to
    know which ones change what.

    The exception is the two form-driven flows: their confirm button belongs to a dialog
    this object owns, not to the calling view, so those call `on_changed` themselves.
    """

    def __init__(
        self,
        imports: ImportCoordinator,
        task_service: TaskService,
        transcript_service: TranscriptService,
        chronicle_service: ChronicleService,
        picker: FilePickerFlow,
        show_snackbar: Callable[[str], None],
        get_page: Callable[[], ft.Page],
        on_changed: Callable[[], Awaitable[None]] | None = None,
    ):
        self.imports = imports
        self.task_service = task_service
        self.transcript_service = transcript_service
        self.chronicle_service = chronicle_service
        self.picker = picker
        self.show_snackbar = show_snackbar
        self.get_page = get_page
        self.on_changed = on_changed

        self.edit_form = EditChronicleForm(on_cancel=self.cancel_edit, on_save=self._save_clicked)
        self.transcript_form = TranscriptImportForm(
            on_cancel=self.cancel_transcript_import, on_import=self._import_clicked
        )
        self._pending: Chronicle | None = None

    @property
    def forms(self) -> list[EditChronicleForm | TranscriptImportForm]:
        """The overlay dialogs the hosting view has to attach and detach."""
        return [self.edit_form, self.transcript_form]

    # -- tasks ----------------------------------------------------------------

    async def clean(self, chronicle: Chronicle) -> bool:
        await self.task_service.queue_clean(chronicle.id)
        self.show_snackbar(t("actions.clean_queued"))
        return True

    async def identify_speakers(self, chronicle: Chronicle) -> bool:
        count = await self.transcript_service.refresh_speaker_count(chronicle.id)
        self.show_snackbar(t("actions.speakers_found", count=count))
        return True

    # -- imports --------------------------------------------------------------

    async def import_audio(self, chronicle: Chronicle | None) -> bool:
        """`chronicle` is None from the archive header, which creates one from the file."""
        path = await self.picker.pick_file(AUDIO_EXTENSIONS)
        if not path:
            return False
        return await self._report(
            self.imports.import_audio(chronicle.id if chronicle else None, path)
        )

    async def begin_transcript_import(self, chronicle: Chronicle | None) -> None:
        self._pending = chronicle
        self.transcript_form.open(self.get_page())

    async def cancel_transcript_import(self, _event=None) -> None:
        self.transcript_form.close(self.get_page())

    async def _import_clicked(self, _event) -> None:
        await self._notify(await self.finish_transcript_import())

    async def finish_transcript_import(self) -> bool:
        """
        Closes the options form before opening the picker: two native dialogs stacked on
        each other is what this ordering avoids.
        """
        self.transcript_form.close(self.get_page())
        path = await self.picker.pick_file(TRANSCRIPT_EXTENSIONS)
        if not path:
            return False

        chronicle = self._pending
        self._pending = None
        return await self._report(
            self.imports.import_transcript(
                chronicle.id if chronicle else None,
                path,
                self.transcript_form.options(),
                self._ask_overwrite_or_append,
            )
        )

    async def link_chronicle(self) -> bool:
        path = await self.picker.pick_file(PROJECT_EXTENSIONS)
        if not path:
            return False
        return await self._report(self.imports.link_chronicle(path))

    async def _ask_overwrite_or_append(self) -> str:
        return await ask_choice(
            self.get_page(),
            t("actions.transcript_exists_title"),
            t("actions.transcript_exists_message"),
            [
                Choice(t("common.cancel"), "cancel"),
                Choice(t("actions.append"), "append"),
                Choice(t("actions.overwrite"), "overwrite", primary=True),
            ],
        )

    async def _report(self, work: Awaitable[str | None]) -> bool:
        """Runs one import, showing whatever it says. True either way - the list reloads."""
        try:
            message = await work
        except Exception as error:
            logger.exception("A chronicle import failed")
            self.show_snackbar(t("actions.failed", error=error))
            return True
        if message:
            self.show_snackbar(message)
        return True

    # -- metadata -------------------------------------------------------------

    async def begin_edit(self, chronicle: Chronicle) -> None:
        self._pending = chronicle
        self.edit_form.fill_from(chronicle)
        self.edit_form.open(self.get_page())

    async def cancel_edit(self, _event=None) -> None:
        self.edit_form.close(self.get_page())

    async def _save_clicked(self, _event) -> None:
        await self._notify(await self.finish_edit())

    async def _notify(self, changed: bool) -> None:
        if changed and self.on_changed is not None:
            await self.on_changed()

    async def finish_edit(self) -> bool:
        self.edit_form.close(self.get_page())
        pending = self._pending
        self._pending = None
        if pending is None:
            return False

        chronicle = await self.chronicle_service.get_chronicle(pending.id)
        if chronicle is None:
            self.show_snackbar(t("actions.gone"))
            return True

        await self.chronicle_service.update_chronicle(self.edit_form.apply_to(chronicle))
        self.show_snackbar(t("actions.updated"))
        return True

    async def delete(self, chronicle: Chronicle) -> bool:
        if not await confirm(
            self.get_page(),
            t("actions.delete_title"),
            t("actions.delete_message", title=chronicle.title),
            confirm_label=t("common.delete"),
        ):
            return False

        try:
            await self.chronicle_service.delete_chronicle(chronicle.id)
        except Exception as error:
            # Removing the files can still fail after the databases are closed - a file
            # held open by something else on Windows is the usual reason. The chronicle
            # may already be gone from the archive, so the view reloads either way.
            logger.exception("Deleting a chronicle failed")
            self.show_snackbar(t("actions.delete_failed", error=error))
            return True

        self.show_snackbar(t("actions.deleted", title=chronicle.title))
        return True
