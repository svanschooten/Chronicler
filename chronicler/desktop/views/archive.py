import logging
import os
from collections.abc import Callable

import flet as ft

from chronicler.core.models import Chronicle
from chronicler.core.services.chronicle_service import ChronicleService
from chronicler.core.services.task_service import TaskService

logger = logging.getLogger(__name__)


class ArchiveView(ft.Column):
    def __init__(
        self,
        chronicle_service: ChronicleService,
        task_service: TaskService,
        on_open_chronicle: Callable[[Chronicle], None],
    ):
        logger.debug("ArchiveView constructed")
        self.chronicle_service = chronicle_service
        self.task_service = task_service
        self.on_open_chronicle = on_open_chronicle
        self.query = ""
        self.file_picker = None
        self.picker_action = None
        self.current_chronicle_id = None

        self.chronicle_list = ft.Column(spacing=12, scroll=ft.ScrollMode.ADAPTIVE, expand=True)

        self.new_chronicle_name = ft.TextField(label="Chronicle Title")
        self.create_dialog = ft.AlertDialog(
            title=ft.Text("Create New Chronicle"),
            content=self.new_chronicle_name,
            actions=[
                ft.TextButton("Cancel", on_click=self.close_dialog),
                ft.TextButton("Create", on_click=self.create_chronicle_clicked),
            ],
        )

        self.transcript_regex = ft.TextField(
            label="Line Regex",
            value=r"^([A-Za-z0-9 _]+)\s*:(.*)$",
            hint_text=r"e.g. ^([A-Z]+):\s+(.*)$",
        )
        self.transcript_speaker_group = ft.TextField(label="Speaker Group Index", value="1")
        self.transcript_text_group = ft.TextField(label="Text Group Index", value="2")

        self.transcript_dialog = ft.AlertDialog(
            title=ft.Text("Import Transcript"),
            content=ft.Column(
                [
                    self.transcript_regex,
                    self.transcript_speaker_group,
                    self.transcript_text_group,
                ],
                tight=True,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=self.close_transcript_dialog),
                ft.TextButton("Select File & Import", on_click=self.do_transcript_import),
            ],
        )

        super().__init__(
            expand=True,
            spacing=16,
            controls=[
                ft.Row(
                    controls=[
                        ft.Column(
                            controls=[
                                ft.Text("Chronicles", size=30, weight=ft.FontWeight.BOLD),
                                ft.Text(
                                    "Your self-contained conversation projects.",
                                    color=ft.Colors.GREY_400,
                                ),
                            ],
                        ),
                        ft.PopupMenuButton(
                            content=ft.Container(
                                content=ft.Row(
                                    [
                                        ft.Icon(ft.Icons.ADD, color=ft.Colors.BROWN_900),
                                        ft.Text(
                                            "Import",
                                            color=ft.Colors.BROWN_900,
                                            weight=ft.FontWeight.BOLD,
                                        ),
                                    ],
                                    alignment=ft.MainAxisAlignment.CENTER,
                                ),
                                bgcolor=ft.Colors.AMBER_700,
                                padding=ft.Padding(left=16, top=8, right=16, bottom=8),
                                border_radius=8,
                            ),
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
                        ft.ElevatedButton(
                            content=ft.Text("New Chronicle"),
                            icon=ft.Icons.ADD,
                            on_click=self.show_create_dialog,
                            style=ft.ButtonStyle(
                                bgcolor=ft.Colors.AMBER_700,
                                color=ft.Colors.BROWN_900,
                            ),
                        ),
                        ft.IconButton(ft.Icons.REFRESH, on_click=self.refresh_clicked),
                    ],
                ),
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.SEARCH, color=ft.Colors.GREY_400),
                        ft.TextField(
                            expand=True,
                            hint_text="Search chronicles",
                            on_change=self.search_changed,
                        ),
                    ],
                ),
                self.chronicle_list,
            ],
        )

    def did_mount(self):
        logger.debug("ArchiveView loaded")
        self.page.run_task(self.mount_async)

    async def mount_async(self):
        logger.debug("ArchiveView.mount_async started")
        # Ensure required controls are in the overlay
        if self.file_picker is None:
            self.file_picker = ft.FilePicker()

        if self.create_dialog not in self.page.overlay:
            self.page.overlay.append(self.create_dialog)

        if self.transcript_dialog not in self.page.overlay:
            self.page.overlay.append(self.transcript_dialog)

        self.page.update()
        await self.load_chronicles()
        logger.debug("ArchiveView.mount_async finished")

    def will_unmount(self):
        logger.debug("ArchiveView unloaded")
        if self.create_dialog in self.page.overlay:
            self.page.overlay.remove(self.create_dialog)
        if self.transcript_dialog in self.page.overlay:
            self.page.overlay.remove(self.transcript_dialog)
        if self.file_picker and self.file_picker in self.page.overlay:
            self.page.overlay.remove(self.file_picker)
        self.page.update()

    async def refresh_clicked(self, e):
        await self.load_chronicles()

    async def import_audio_clicked(self, e, chronicle_id=None):
        self.picker_action = "AUDIO"
        self.current_chronicle_id = chronicle_id
        await self.pick_file(allowed_extensions=["mp3", "wav", "m4a"])

    async def import_transcript_clicked(self, e, chronicle_id=None):
        self.current_chronicle_id = chronicle_id
        self.transcript_dialog.open = True
        self.page.update()

    async def close_transcript_dialog(self, e=None):
        self.transcript_dialog.open = False
        self.page.update()

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
        try:
            if self.picker_action == "AUDIO":
                if self.current_chronicle_id:
                    await self.task_service.queue_import(self.current_chronicle_id, file_path)
                    self.show_snackbar("Audio import task queued")
                else:
                    title = os.path.basename(file_path).rsplit(".", 1)[0]
                    chronicle = await self.chronicle_service.create_chronicle(
                        title, source_file=file_path
                    )
                    await self.task_service.queue_import(chronicle.id, file_path)
                    self.show_snackbar(f"Created '{title}' and queued audio import")

            elif self.picker_action == "TRANSCRIPT":
                regex = self.transcript_regex.value
                speaker_group = int(self.transcript_speaker_group.value or 1)
                text_group = int(self.transcript_text_group.value or 2)

                if self.current_chronicle_id:
                    await self.task_service.queue_import(
                        self.current_chronicle_id,
                        file_path,
                        regex=regex,
                        speaker_group=speaker_group,
                        text_group=text_group,
                    )
                    self.show_snackbar("Transcript import task queued")
                else:
                    title = os.path.basename(file_path).rsplit(".", 1)[0]
                    chronicle = await self.chronicle_service.create_chronicle(title)
                    await self.task_service.queue_import(
                        chronicle.id,
                        file_path,
                        regex=regex,
                        speaker_group=speaker_group,
                        text_group=text_group,
                    )
                    self.show_snackbar(f"Created '{title}' and queued transcript import")

            elif self.picker_action == "LINK":
                title = os.path.basename(os.path.dirname(file_path))
                if title == "chronicles" or not title:
                    title = os.path.basename(file_path).rsplit(".", 1)[0]

                await self.chronicle_service.create_chronicle(title, project_path=file_path)
                self.show_snackbar(f"Linked external chronicle '{title}'")

            await self.load_chronicles()
        except Exception as ex:
            logger.error(f"Error handling file result: {ex}")
            self.show_snackbar(f"Error: {ex}")
        finally:
            self.picker_action = None
            self.current_chronicle_id = None

    async def clean_clicked(self, chronicle_id):
        await self.task_service.queue_clean(chronicle_id)
        self.show_snackbar("Clean task queued")

    def show_snackbar(self, message: str):
        self.page.snack_bar = ft.SnackBar(ft.Text(message))
        self.page.snack_bar.open = True
        self.page.update()

    async def show_create_dialog(self, e):
        self.create_dialog.open = True
        self.page.update()

    async def close_dialog(self, e=None):
        self.create_dialog.open = False
        self.page.update()

    async def create_chronicle_clicked(self, e):
        if self.new_chronicle_name.value:
            await self.chronicle_service.create_chronicle(self.new_chronicle_name.value)
            self.new_chronicle_name.value = ""
            await self.close_dialog()
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

    async def open_chronicle_clicked(self, e):
        await self.on_open_chronicle(e.control.data)

    def create_chronicle_card(self, item: Chronicle) -> ft.Container:
        tags = " · ".join([t.name for t in item.tags]) if item.tags else "No tags"
        return ft.Container(
            bgcolor=ft.Colors.BLUE_GREY_800,
            padding=ft.Padding.all(18),
            border=ft.Border.all(1, ft.Colors.BLUE_GREY_700),
            border_radius=12,
            on_click=self.open_chronicle_clicked,
            data=item,
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text(
                                (item.kind or "Unknown").upper(),
                                size=12,
                                weight=ft.FontWeight.BOLD,
                                color=ft.Colors.GREY_400,
                            ),
                            ft.Text(item.status or "Imported", size=12, color=ft.Colors.GREY_400),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Text(item.title, size=18, weight=ft.FontWeight.BOLD),
                    ft.Text(
                        item.description or "No description",
                        max_lines=2,
                        color=ft.Colors.GREY_400,
                    ),
                    ft.Row(
                        controls=[
                            ft.Text(item.created_at.strftime("%Y-%m-%d"), color=ft.Colors.GREY_400),
                            ft.Text(item.duration or "Unknown duration", color=ft.Colors.GREY_400),
                            ft.Text(f"{item.speakers_count} speakers", color=ft.Colors.GREY_400),
                        ],
                        wrap=True,
                        spacing=10,
                    ),
                    ft.Text(tags, color=ft.Colors.GREY_400),
                    ft.Row(
                        controls=[
                            ft.PopupMenuButton(
                                icon=ft.Icons.UPLOAD_FILE,
                                items=[
                                    ft.PopupMenuItem(
                                        content=ft.Text("Import Audio"),
                                        icon=ft.Icons.AUDIO_FILE,
                                        on_click=lambda e, i=item.id: self.import_audio_clicked(
                                            e, i
                                        ),
                                    ),
                                    ft.PopupMenuItem(
                                        content=ft.Text("Import Transcript"),
                                        icon=ft.Icons.DESCRIPTION,
                                        on_click=lambda e, i=item.id: (
                                            self.import_transcript_clicked(e, i)
                                        ),
                                    ),
                                ],
                                tooltip="Import to this chronicle",
                            ),
                            ft.IconButton(
                                icon=ft.Icons.CLEANING_SERVICES,
                                on_click=lambda _, i=item.id: self.clean_clicked(i),
                                tooltip="Clean transcript",
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                    ),
                ],
            ),
        )
