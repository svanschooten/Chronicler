import logging
from collections.abc import Awaitable, Callable

import flet as ft

from chronicler.core.models import Chronicle
from chronicler.core.services.chronicle_service import ChronicleService
from chronicler.core.services.task_service import TaskService
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.desktop.forms import CreateChronicleForm
from chronicler.desktop.imports import ImportCoordinator
from chronicler.desktop.operations import ChronicleOperations
from chronicler.desktop.picking import FilePickerFlow
from chronicler.desktop.theme import theme_colors
from chronicler.desktop.views.archive.cards import ChronicleCardHandlers, chronicle_card
from chronicler.desktop.widgets import amber_button
from chronicler.i18n import t

logger = logging.getLogger(__name__)


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
        self.query = ""
        self.file_picker: ft.FilePicker | None = None
        self.picker = FilePickerFlow(lambda: self.file_picker, self.show_snackbar)

        self.chronicle_list = ft.Column(spacing=12, scroll=ft.ScrollMode.ADAPTIVE, expand=True)

        self.create_form = CreateChronicleForm(
            on_cancel=self.close_create_dialog, on_create=self.create_chronicle_clicked
        )
        self.operations = ChronicleOperations(
            ImportCoordinator(chronicle_service, task_service, transcript_service, stage_file),
            task_service,
            transcript_service,
            chronicle_service,
            self.picker,
            self.show_snackbar,
            lambda: self.page,
            on_changed=self.load_chronicles,
        )

        super().__init__(expand=True, spacing=16, controls=self._build_controls())

    def _build_controls(self) -> list[ft.Control]:
        return [
            ft.Row(
                controls=[
                    ft.Column(
                        controls=[
                            ft.Text(
                                t("archive.title"),
                                size=30,
                                weight=ft.FontWeight.BOLD,
                                color=self.colors.text,
                            ),
                            ft.Text(t("archive.subtitle"), color=self.colors.muted),
                        ],
                    ),
                    ft.PopupMenuButton(
                        content=amber_button(t("archive.import"), ft.Icons.ADD, dropdown=True),
                        items=[
                            ft.PopupMenuItem(
                                content=ft.Text(t("actions.import_audio")),
                                icon=ft.Icons.AUDIO_FILE,
                                on_click=self.import_audio_clicked,
                            ),
                            ft.PopupMenuItem(
                                content=ft.Text(t("actions.import_transcript")),
                                icon=ft.Icons.DESCRIPTION,
                                on_click=self.import_transcript_clicked,
                            ),
                            ft.PopupMenuItem(
                                content=ft.Text(t("archive.link")),
                                icon=ft.Icons.LINK,
                                on_click=self.link_chronicle_clicked,
                            ),
                        ],
                    ),
                    amber_button(t("archive.new"), ft.Icons.ADD, on_click=self.show_create_dialog),
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
                        hint_text=t("archive.search"),
                        color=self.colors.text,
                        on_change=self.search_changed,
                    ),
                ],
            ),
            self.chronicle_list,
        ]

    @property
    def _forms(self) -> list:
        return [self.create_form, *self.operations.forms]

    def did_mount(self):
        logger.debug("ArchiveView loaded")
        self.page.run_task(self.mount_async)

    async def mount_async(self):
        logger.debug("ArchiveView.mount_async started")
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
        self.page.show_dialog(ft.SnackBar(ft.Text(message)))

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
                self.chronicle_list.controls = [ft.Text(t("archive.empty"))]
            self.update()
        except Exception as e:
            logger.exception(f"Error loading chronicles: {e}")
            self.chronicle_list.controls = [ft.Text(t("archive.load_failed", error=e))]
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
        await self.operations.begin_edit(e.control.data)

    async def delete_clicked(self, e):
        if await self.operations.delete(e.control.data):
            await self.load_chronicles()

    async def clean_clicked(self, e):
        await self.operations.clean(e.control.data)

    async def identify_speakers_clicked(self, e):
        if await self.operations.identify_speakers(e.control.data):
            await self.load_chronicles()

    async def import_audio_clicked(self, e):
        if await self.operations.import_audio(e.control.data):
            await self.load_chronicles()

    async def import_transcript_clicked(self, e):
        await self.operations.begin_transcript_import(e.control.data)

    async def link_chronicle_clicked(self, e):
        if await self.operations.link_chronicle():
            await self.load_chronicles()
