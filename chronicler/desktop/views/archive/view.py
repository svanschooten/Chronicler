import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

import flet as ft

from chronicler.core.models import Chronicle
from chronicler.core.services.chronicle_service import ChronicleService
from chronicler.core.services.task_service import TaskService
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.desktop.dialogs import Choice, ask_choice, confirm
from chronicler.desktop.theme import theme_colors
from chronicler.desktop.views.archive.cards import ChronicleCardHandlers, chronicle_card
from chronicler.desktop.views.archive.forms import (
    CreateChronicleForm,
    EditChronicleForm,
    TranscriptImportForm,
)
from chronicler.desktop.views.archive.imports import ImportCoordinator
from chronicler.desktop.widgets import amber_button

logger = logging.getLogger(__name__)

#: What the pending file-picker result should be used for. Set before opening the
#: picker and consumed by handle_file_result, because Flet's picker result arrives
#: without any indication of which action asked for it.
PickerAction = str


class ArchiveView(ft.Column):
    def __init__(
        self,
        chronicle_service: ChronicleService,
        task_service: TaskService,
        on_open_chronicle: Callable[[Chronicle], Awaitable[None]],
        stage_file: Callable[[str], Awaitable[str]],
        transcript_service: TranscriptService,
        dark_mode: bool = True,
    ):
        logger.debug("ArchiveView constructed")
        self.chronicle_service = chronicle_service
        self.task_service = task_service
        self.transcript_service = transcript_service
        self.on_open_chronicle = on_open_chronicle
        self.colors = theme_colors(dark_mode)
        self.imports = ImportCoordinator(
            chronicle_service, task_service, transcript_service, stage_file
        )

        self.query = ""
        self.file_picker: ft.FilePicker | None = None
        self.picker_action: PickerAction | None = None
        self.current_chronicle_id: UUID | None = None
        self.editing_chronicle_id: UUID | None = None

        self.chronicle_list = ft.Column(spacing=12, scroll=ft.ScrollMode.ADAPTIVE, expand=True)

        self.create_form = CreateChronicleForm(
            on_cancel=self.close_create_dialog, on_create=self.create_chronicle_clicked
        )
        self.edit_form = EditChronicleForm(
            on_cancel=self.close_edit_dialog, on_save=self.save_edit_clicked
        )
        self.transcript_form = TranscriptImportForm(
            on_cancel=self.close_transcript_dialog, on_import=self.do_transcript_import
        )

        super().__init__(expand=True, spacing=16, controls=self._build_controls())

    # -- layout ---------------------------------------------------------------

    def _build_controls(self) -> list[ft.Control]:
        return [
            ft.Row(
                controls=[
                    ft.Column(
                        controls=[
                            ft.Text(
                                "Chronicles",
                                size=30,
                                weight=ft.FontWeight.BOLD,
                                color=self.colors.text,
                            ),
                            ft.Text(
                                "Your self-contained conversation projects.",
                                color=self.colors.muted,
                            ),
                        ],
                    ),
                    ft.PopupMenuButton(
                        content=amber_button("Import", ft.Icons.ADD, dropdown=True),
                        items=[
                            ft.PopupMenuItem(
                                content=ft.Text("Import Audio"),
                                icon=ft.Icons.AUDIO_FILE,
                                on_click=self.import_audio_clicked,
                            ),
                            ft.PopupMenuItem(
                                content=ft.Text("Import Transcript"),
                                icon=ft.Icons.DESCRIPTION,
                                on_click=self.import_transcript_clicked,
                            ),
                            ft.PopupMenuItem(
                                content=ft.Text("Link External Chronicle"),
                                icon=ft.Icons.LINK,
                                on_click=self.link_chronicle_clicked,
                            ),
                        ],
                    ),
                    amber_button("New Chronicle", ft.Icons.ADD, on_click=self.show_create_dialog),
                    ft.IconButton(
                        ft.Icons.REFRESH,
                        icon_color=self.colors.muted,
                        on_click=self.refresh_clicked,
                    ),
                ],
            ),
            ft.Row(
                controls=[
                    ft.Icon(ft.Icons.SEARCH, color=self.colors.muted),
                    ft.TextField(
                        expand=True,
                        hint_text="Search chronicles",
                        color=self.colors.text,
                        on_change=self.search_changed,
                    ),
                ],
            ),
            self.chronicle_list,
        ]

    @property
    def _forms(self) -> list[CreateChronicleForm | EditChronicleForm | TranscriptImportForm]:
        return [self.create_form, self.edit_form, self.transcript_form]

    # -- lifecycle ------------------------------------------------------------

    def did_mount(self):
        logger.debug("ArchiveView loaded")
        self.page.run_task(self.mount_async)

    async def mount_async(self):
        logger.debug("ArchiveView.mount_async started")
        # FilePicker is a Service, not a visual control - it belongs in
        # page.services, not page.overlay. Putting it in overlay (which expects
        # renderable widgets) makes the client choke with "Unknown control:
        # FilePicker".
        if self.file_picker is None:
            self.file_picker = ft.FilePicker()
        if self.file_picker not in self.page.services:
            self.page.services.append(self.file_picker)

        for form in self._forms:
            form.attach(self.page)

        self.page.update()
        await self.load_chronicles()
        logger.debug("ArchiveView.mount_async finished")

    def will_unmount(self):
        logger.debug("ArchiveView unloaded")
        for form in self._forms:
            form.detach(self.page)
        if self.file_picker and self.file_picker in self.page.services:
            self.page.services.remove(self.file_picker)
        self.page.update()

    def show_snackbar(self, message: str):
        # flet 0.86.4's ft.Page has no `snack_bar` attribute (that was a pre-0.70
        # API) - a SnackBar is a dialog shown through the same stack as ft.AlertDialog.
        self.page.show_dialog(ft.SnackBar(ft.Text(message)))

    # -- chronicle list -------------------------------------------------------

    async def refresh_clicked(self, e):
        await self.load_chronicles()

    async def search_changed(self, e):
        self.query = e.data
        await self.load_chronicles()

    async def load_chronicles(self):
        try:
            if self.query:
                chronicles = await self.chronicle_service.search_chronicles(self.query)
            else:
                chronicles = await self.chronicle_service.list_chronicles()

            self.chronicle_list.controls = [self.create_chronicle_card(c) for c in chronicles]
            if not chronicles:
                self.chronicle_list.controls = [ft.Text("No chronicles found.")]
            self.update()
        except Exception as e:
            logger.exception(f"Error loading chronicles: {e}")
            self.chronicle_list.controls = [ft.Text(f"Error loading chronicles: {e}")]
            self.update()

    def create_chronicle_card(self, item: Chronicle) -> ft.Container:
        return chronicle_card(
            item,
            self.colors,
            ChronicleCardHandlers(
                on_open=self.open_chronicle_clicked,
                on_import_audio=self.import_audio_clicked,
                on_import_transcript=self.import_transcript_clicked,
                on_edit=self.edit_clicked,
                on_clean=self.clean_clicked,
                on_identify_speakers=self.identify_speakers_clicked,
                on_delete=self.delete_clicked,
            ),
        )

    async def open_chronicle_clicked(self, e):
        await self.on_open_chronicle(e.control.data)

    # -- create / edit --------------------------------------------------------

    async def show_create_dialog(self, e):
        self.create_form.open(self.page)

    async def close_create_dialog(self, e=None):
        self.create_form.close(self.page)

    async def create_chronicle_clicked(self, e):
        title = self.create_form.title
        if not title:
            return
        await self.chronicle_service.create_chronicle(title)
        self.create_form.clear()
        await self.close_create_dialog()
        await self.load_chronicles()

    async def edit_clicked(self, e):
        chronicle: Chronicle = e.control.data
        self.editing_chronicle_id = chronicle.id
        self.edit_form.fill_from(chronicle)
        self.edit_form.open(self.page)

    async def close_edit_dialog(self, e=None):
        self.edit_form.close(self.page)

    async def save_edit_clicked(self, e):
        chronicle = await self.chronicle_service.get_chronicle(self.editing_chronicle_id)
        if chronicle is None:
            await self.close_edit_dialog()
            self.show_snackbar("Chronicle no longer exists.")
            return

        await self.chronicle_service.update_chronicle(self.edit_form.apply_to(chronicle))
        await self.close_edit_dialog()
        self.show_snackbar("Chronicle updated")
        await self.load_chronicles()

    async def delete_clicked(self, e):
        chronicle: Chronicle = e.control.data
        confirmed = await confirm(
            self.page,
            "Delete chronicle?",
            f"This permanently deletes '{chronicle.title}', its transcript, and any "
            "queued tasks for it. This cannot be undone.",
        )
        if not confirmed:
            return

        await self.chronicle_service.delete_chronicle(chronicle.id)
        self.show_snackbar(f"Deleted '{chronicle.title}'")
        await self.load_chronicles()

    # -- per-chronicle task actions -------------------------------------------

    async def clean_clicked(self, e):
        await self.task_service.queue_clean(e.control.data)
        self.show_snackbar("Clean task queued")

    async def identify_speakers_clicked(self, e):
        count = await self.transcript_service.refresh_speaker_count(e.control.data)
        self.show_snackbar(f"Found {count} speaker{'s' if count != 1 else ''}")
        await self.load_chronicles()

    # -- importing ------------------------------------------------------------

    async def import_audio_clicked(self, e):
        # The header menu item has no `data` (None -> creates a new chronicle); a
        # card's menu item carries the chronicle id it belongs to via e.control.data.
        self.picker_action = "AUDIO"
        self.current_chronicle_id = e.control.data
        await self.pick_file(allowed_extensions=["mp3", "wav", "m4a"])

    async def import_transcript_clicked(self, e):
        self.current_chronicle_id = e.control.data
        self.transcript_form.open(self.page)

    async def close_transcript_dialog(self, e=None):
        self.transcript_form.close(self.page)

    async def do_transcript_import(self, e):
        await self.close_transcript_dialog()
        self.picker_action = "TRANSCRIPT"
        await self.pick_file(allowed_extensions=["txt"])

    async def link_chronicle_clicked(self, e):
        self.picker_action = "LINK"
        await self.pick_file(allowed_extensions=["db"])

    async def pick_file(self, allowed_extensions=None):
        if self.file_picker is None:
            self.show_snackbar("File picker not available.")
            return

        try:
            result = await self.file_picker.pick_files(
                allowed_extensions=allowed_extensions,
                file_type=ft.FilePickerFileType.CUSTOM
                if allowed_extensions
                else ft.FilePickerFileType.ANY,
            )
            if result:
                await self.handle_file_result(result[0].path)
        except Exception as ex:
            logger.error(f"Error during pick_files: {ex}")
            self.show_snackbar(f"Error picking files: {ex}")

    async def handle_file_result(self, file_path):
        """Dispatches the picked file to whichever import the user asked for. The
        actual work lives in ImportCoordinator; this only translates picker state into
        a call and its result into a snackbar."""
        try:
            message: str | None = None
            if self.picker_action == "AUDIO":
                message = await self.imports.import_audio(self.current_chronicle_id, file_path)
            elif self.picker_action == "TRANSCRIPT":
                message = await self.imports.import_transcript(
                    self.current_chronicle_id,
                    file_path,
                    self.transcript_form.options(),
                    self.ask_overwrite_or_append,
                )
            elif self.picker_action == "LINK":
                message = await self.imports.link_chronicle(file_path)

            if message:
                self.show_snackbar(message)
            await self.load_chronicles()
        except Exception as ex:
            logger.error(f"Error handling file result: {ex}")
            self.show_snackbar(f"Error: {ex}")
        finally:
            self.picker_action = None
            self.current_chronicle_id = None

    async def ask_overwrite_or_append(self) -> str:
        """Asked before a second transcript import can silently destroy the first."""
        return await ask_choice(
            self.page,
            "Transcript already exists",
            "This chronicle already has an imported transcript. Overwrite it with "
            "the new file, or append the new file's lines to the end?",
            [
                Choice("Cancel", "cancel"),
                Choice("Append", "append"),
                Choice("Overwrite", "overwrite", primary=True),
            ],
        )
