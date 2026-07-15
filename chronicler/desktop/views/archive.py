import logging
import os

import flet as ft

from chronicler.core.services.chronicle_service import ChronicleService
from chronicler.core.services.task_service import TaskService

logger = logging.getLogger(__name__)


class ArchiveView(ft.Column):
    def __init__(
        self,
        chronicle_service: ChronicleService,
        task_service: TaskService,
        file_picker: ft.FilePicker,
    ):
        logger.info("ArchiveView constructed")
        self.chronicle_service = chronicle_service
        self.task_service = task_service
        self.file_picker = file_picker
        self.chronicle_list = ft.Column(scroll=ft.ScrollMode.ADAPTIVE, expand=True)

        self.new_chronicle_name = ft.TextField(label="Chronicle Title")
        self.create_dialog = ft.AlertDialog(
            title=ft.Text("Create New Chronicle"),
            content=self.new_chronicle_name,
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.page.run_task(self.close_dialog)),
                ft.TextButton("Create", on_click=self.create_chronicle_clicked),
            ],
        )

        super().__init__(
            controls=[
                ft.Row(
                    [
                        ft.Text("Archive", style=ft.TextThemeStyle.HEADLINE_MEDIUM),
                        ft.Row(
                            [
                                ft.IconButton(
                                    ft.Icons.UPLOAD_FILE,
                                    tooltip="Import Transcript (as new Chronicle)",
                                    on_click=self.global_import_clicked,
                                ),
                                ft.IconButton(ft.Icons.ADD, on_click=self.show_create_dialog),
                                ft.IconButton(ft.Icons.REFRESH, on_click=self.refresh_clicked),
                            ]
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Divider(),
                self.chronicle_list,
            ],
            expand=True,
        )

    def did_mount(self):
        logger.info("ArchiveView loaded")
        self.page.run_task(self.mount_async)

    async def mount_async(self):
        # Ensure required controls are in the overlay
        if self.create_dialog not in self.page.overlay:
            self.page.overlay.append(self.create_dialog)

        self.page.update()
        await self.load_chronicles()

    def will_unmount(self):
        logger.info("ArchiveView unloaded")
        if self.create_dialog in self.page.overlay:
            self.page.overlay.remove(self.create_dialog)
        self.page.update()

    async def refresh_clicked(self, e):
        await self.load_chronicles()

    async def global_import_clicked(self, e):
        result = await self.file_picker.pick_files(
            allowed_extensions=["txt"], file_type=ft.FilePickerFileType.CUSTOM
        )
        if result:
            file_path = result[0].path
            # Create a chronicle with the file name
            title = os.path.basename(file_path).rsplit(".", 1)[0]
            chronicle = await self.chronicle_service.create_chronicle(title)
            await self.task_service.queue_import(chronicle.id, file_path)
            self.show_snackbar(f"Created '{title}' and queued import")
            await self.load_chronicles()

    async def import_clicked(self, chronicle_id):
        result = await self.file_picker.pick_files(
            allowed_extensions=["txt"], file_type=ft.FilePickerFileType.CUSTOM
        )
        if result:
            file_path = result[0].path
            await self.task_service.queue_import(chronicle_id, file_path)
            self.show_snackbar("Import task queued")

    async def clean_clicked(self, chronicle_id):
        await self.task_service.queue_clean(chronicle_id)
        self.show_snackbar("Clean task queued")

    def show_snackbar(self, message: str):
        sb = ft.SnackBar(ft.Text(message))
        self.page.overlay.append(sb)
        sb.open = True
        self.page.update()

    async def show_create_dialog(self, e):
        self.create_dialog.open = True
        self.page.update()

    async def close_dialog(self):
        self.create_dialog.open = False
        self.page.update()

    async def create_chronicle_clicked(self, e):
        if self.new_chronicle_name.value:
            await self.chronicle_service.create_chronicle(self.new_chronicle_name.value)
            self.new_chronicle_name.value = ""
            await self.close_dialog()
            await self.load_chronicles()

    async def load_chronicles(self):
        try:
            chronicles = await self.chronicle_service.list_chronicles()
            self.chronicle_list.controls = [
                ft.ListTile(
                    title=ft.Text(c.title),
                    subtitle=ft.Text(c.description or "No description"),
                    leading=ft.Icon(ft.Icons.BOOK),
                    trailing=ft.Row(
                        [
                            ft.IconButton(
                                ft.Icons.UPLOAD_FILE,
                                tooltip="Import Transcript",
                                on_click=lambda _, cid=c.id: self.import_clicked(cid),
                            ),
                            ft.IconButton(
                                ft.Icons.CLEANING_SERVICES,
                                tooltip="Queue Clean",
                                on_click=lambda _, cid=c.id: self.clean_clicked(cid),
                            ),
                        ],
                        tight=True,
                    ),
                )
                for c in chronicles
            ]
            if not chronicles:
                self.chronicle_list.controls = [ft.Text("No chronicles found.")]
            self.update()
        except Exception as e:
            print(f"Error loading chronicles: {e}")
            self.chronicle_list.controls = [ft.Text(f"Error loading chronicles: {e}")]
            self.update()
