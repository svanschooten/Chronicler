"""
The chronicle-level action row shown above a transcript.

Everything here also exists on the archive card. It is repeated in the chronicle view
because that is where a chronicle is actually worked on - going back to the list to clean
or import into the thing already open is the awkward part being fixed. See docs/desktop.md.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import flet as ft

from chronicler.core.models import Chronicle
from chronicler.core.services.chronicle_service import ChronicleService
from chronicler.core.services.task_service import TaskService
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.desktop.dialogs import Choice, ask_choice, confirm
from chronicler.desktop.forms import EditChronicleForm, TranscriptImportForm
from chronicler.desktop.imports import ImportCoordinator
from chronicler.desktop.picking import FilePickerFlow
from chronicler.desktop.theme import ThemeColors
from chronicler.i18n import t

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = ["mp3", "wav", "m4a", "flac", "ogg"]
TRANSCRIPT_EXTENSIONS = ["txt"]


@dataclass(frozen=True)
class ChronicleActionCallbacks:
    """What the row asks the view to do once it has changed something."""

    on_changed: Callable[[], Awaitable[None]]
    on_deleted: Callable[[], Awaitable[None]]
    on_summarize: Callable[[], Awaitable[None]]


class ChronicleActions(ft.Row):
    def __init__(
        self,
        chronicle: Chronicle,
        imports: ImportCoordinator,
        task_service: TaskService,
        transcript_service: TranscriptService,
        chronicle_service: ChronicleService,
        picker: FilePickerFlow,
        colors: ThemeColors,
        show_snackbar: Callable[[str], None],
        callbacks: ChronicleActionCallbacks,
        can_summarize: Callable[[], bool] | None = None,
    ):
        self.chronicle = chronicle
        self.imports = imports
        self.task_service = task_service
        self.transcript_service = transcript_service
        self.chronicle_service = chronicle_service
        self.picker = picker
        self.colors = colors
        self.show_snackbar = show_snackbar
        self.callbacks = callbacks
        self.can_summarize = can_summarize or (lambda: True)

        self.edit_form = EditChronicleForm(
            on_cancel=self.edit_cancelled, on_save=self.edit_save_clicked
        )
        self.transcript_form = TranscriptImportForm(
            on_cancel=self.transcript_import_cancelled, on_import=self.transcript_import_confirmed
        )

        super().__init__(wrap=True, spacing=4, controls=self._build())

    @property
    def forms(self) -> list[EditChronicleForm | TranscriptImportForm]:
        """The overlay dialogs the hosting view has to attach and detach."""
        return [self.edit_form, self.transcript_form]

    def _build(self) -> list[ft.Control]:
        summarize_allowed = self.can_summarize()
        return [
            self._action(ft.Icons.AUDIO_FILE, "actions.import_audio", self.import_audio_clicked),
            self._action(
                ft.Icons.DESCRIPTION, "actions.import_transcript", self.import_transcript_clicked
            ),
            self._action(ft.Icons.CLEANING_SERVICES, "actions.clean", self.clean_clicked),
            self._action(
                ft.Icons.RECORD_VOICE_OVER,
                "actions.identify_speakers",
                self.identify_speakers_clicked,
            ),
            self._action(
                ft.Icons.AUTO_AWESOME,
                "actions.summarize",
                self.summarize_clicked,
                enabled=summarize_allowed,
                disabled_tooltip="actions.summarize_unavailable",
            ),
            ft.Container(width=8),
            self._action(ft.Icons.EDIT, "actions.edit", self.edit_clicked),
            self._action(ft.Icons.DELETE_OUTLINE, "actions.delete", self.delete_clicked),
        ]

    def _action(
        self,
        icon: ft.IconData,
        key: str,
        on_click,
        enabled: bool = True,
        disabled_tooltip: str | None = None,
    ) -> ft.IconButton:
        return ft.IconButton(
            icon=icon,
            icon_color=self.colors.muted if enabled else self.colors.border,
            tooltip=t(key) if enabled else t(disabled_tooltip or key),
            disabled=not enabled,
            on_click=on_click,
        )

    # -- tasks ----------------------------------------------------------------

    async def clean_clicked(self, e):
        await self.task_service.queue_clean(self.chronicle.id)
        self.show_snackbar(t("actions.clean_queued"))

    async def identify_speakers_clicked(self, e):
        count = await self.transcript_service.refresh_speaker_count(self.chronicle.id)
        self.show_snackbar(t("actions.speakers_found", count=count))
        await self.callbacks.on_changed()

    async def summarize_clicked(self, e):
        await self.callbacks.on_summarize()

    # -- imports --------------------------------------------------------------

    async def import_audio_clicked(self, e):
        path = await self.picker.pick_file(AUDIO_EXTENSIONS)
        if not path:
            return
        await self._report(self.imports.import_audio(self.chronicle.id, path))

    async def import_transcript_clicked(self, e):
        self.transcript_form.open(self.page)

    async def transcript_import_cancelled(self, e=None):
        self.transcript_form.close(self.page)

    async def transcript_import_confirmed(self, e):
        self.transcript_form.close(self.page)
        path = await self.picker.pick_file(TRANSCRIPT_EXTENSIONS)
        if not path:
            return
        await self._report(
            self.imports.import_transcript(
                self.chronicle.id,
                path,
                self.transcript_form.options(),
                self._ask_overwrite_or_append,
            )
        )

    async def _ask_overwrite_or_append(self) -> str:
        return await ask_choice(
            self.page,
            t("actions.transcript_exists_title"),
            t("actions.transcript_exists_message"),
            [
                Choice(t("common.cancel"), "cancel"),
                Choice(t("actions.append"), "append"),
                Choice(t("actions.overwrite"), "overwrite", primary=True),
            ],
        )

    async def _report(self, work: Awaitable[str | None]) -> None:
        """Runs one import, showing whatever it says and reloading the view after."""
        try:
            message = await work
        except Exception as error:
            logger.exception("A chronicle import failed")
            self.show_snackbar(t("actions.failed", error=error))
            return
        if message:
            self.show_snackbar(message)
        await self.callbacks.on_changed()

    # -- metadata -------------------------------------------------------------

    async def edit_clicked(self, e):
        self.edit_form.fill_from(self.chronicle)
        self.edit_form.open(self.page)

    async def edit_cancelled(self, e=None):
        self.edit_form.close(self.page)

    async def edit_save_clicked(self, e):
        self.edit_form.close(self.page)
        chronicle = await self.chronicle_service.get_chronicle(self.chronicle.id)
        if chronicle is None:
            self.show_snackbar(t("actions.gone"))
            return

        await self.chronicle_service.update_chronicle(self.edit_form.apply_to(chronicle))
        self.show_snackbar(t("actions.updated"))
        await self.callbacks.on_changed()

    async def delete_clicked(self, e):
        if not await confirm(
            self.page,
            t("actions.delete_title"),
            t("actions.delete_message", title=self.chronicle.title),
            confirm_label=t("common.delete"),
        ):
            return

        await self.chronicle_service.delete_chronicle(self.chronicle.id)
        self.show_snackbar(t("actions.deleted", title=self.chronicle.title))
        await self.callbacks.on_deleted()
