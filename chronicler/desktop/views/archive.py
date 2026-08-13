import asyncio
import logging
import os
from collections.abc import Awaitable, Callable

import flet as ft

from chronicler.core.models import Chronicle
from chronicler.core.services.chronicle_service import ChronicleService
from chronicler.core.services.task_service import TaskService
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.desktop.theme import theme_colors
from chronicler.desktop.widgets import amber_button

logger = logging.getLogger(__name__)


class ArchiveView(ft.Column):
    def __init__(
        self,
        chronicle_service: ChronicleService,
        task_service: TaskService,
        on_open_chronicle: Callable[[Chronicle], None],
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
        # Picked files can be anywhere on disk (e.g. ~/Downloads); handle_import
        # requires file_path be inside the workspace's imports directory. stage_file
        # copies (local mode) or uploads (thin client mode, once wired) the picked
        # file there first and returns the path actually safe to queue.
        self.stage_file = stage_file
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

        self.editing_chronicle_id = None
        self.edit_title = ft.TextField(label="Title")
        self.edit_description = ft.TextField(label="Description", multiline=True)
        self.edit_kind = ft.TextField(label="Kind", hint_text="e.g. Podcast, D&D session, Meeting")
        self.edit_duration = ft.TextField(label="Duration", hint_text="e.g. 1h 24m")
        self.edit_dialog = ft.AlertDialog(
            title=ft.Text("Edit Chronicle"),
            content=ft.Column(
                [self.edit_title, self.edit_description, self.edit_kind, self.edit_duration],
                tight=True,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=self.close_edit_dialog),
                ft.TextButton("Save", on_click=self.save_edit_clicked),
            ],
        )

        self.transcript_regex = ft.TextField(
            label="Line Regex",
            value=r"^([A-Za-z0-9 _]+)\s*:(.*)$",
            hint_text=r"e.g. ^([A-Z]+):\s+(.*)$",
        )
        self.transcript_speaker_group = ft.TextField(label="Speaker Group Index", value="1")
        self.transcript_text_group = ft.TextField(label="Text Group Index", value="2")
        self.transcript_timestamp_group = ft.TextField(
            label="Timestamp Group Index (optional)",
            hint_text="e.g. 3 for ^([A-Za-z]+):\\s*(.*)\\s+\\[(\\d\\d:\\d\\d:\\d\\d)\\]$ - "
            "leave blank for no timestamps",
        )

        self.transcript_dialog = ft.AlertDialog(
            title=ft.Text("Import Transcript"),
            content=ft.Column(
                [
                    self.transcript_regex,
                    self.transcript_speaker_group,
                    self.transcript_text_group,
                    self.transcript_timestamp_group,
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
                        amber_button(
                            "New Chronicle", ft.Icons.ADD, on_click=self.show_create_dialog
                        ),
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
            ],
        )

    def did_mount(self):
        logger.debug("ArchiveView loaded")
        self.page.run_task(self.mount_async)

    async def mount_async(self):
        logger.debug("ArchiveView.mount_async started")
        # Ensure required controls are registered. FilePicker is a Service, not a
        # visual control - it belongs in page.services, not page.overlay. Putting it
        # in overlay (which expects renderable widgets) makes the client choke with
        # "Unknown control: FilePicker".
        if self.file_picker is None:
            self.file_picker = ft.FilePicker()
        if self.file_picker not in self.page.services:
            self.page.services.append(self.file_picker)

        if self.create_dialog not in self.page.overlay:
            self.page.overlay.append(self.create_dialog)

        if self.transcript_dialog not in self.page.overlay:
            self.page.overlay.append(self.transcript_dialog)

        if self.edit_dialog not in self.page.overlay:
            self.page.overlay.append(self.edit_dialog)

        self.page.update()
        await self.load_chronicles()
        logger.debug("ArchiveView.mount_async finished")

    def will_unmount(self):
        logger.debug("ArchiveView unloaded")
        if self.create_dialog in self.page.overlay:
            self.page.overlay.remove(self.create_dialog)
        if self.transcript_dialog in self.page.overlay:
            self.page.overlay.remove(self.transcript_dialog)
        if self.edit_dialog in self.page.overlay:
            self.page.overlay.remove(self.edit_dialog)
        if self.file_picker and self.file_picker in self.page.services:
            self.page.services.remove(self.file_picker)
        self.page.update()

    async def refresh_clicked(self, e):
        await self.load_chronicles()

    async def import_audio_clicked(self, e):
        # Header menu item has no `data` (None -> creates a new chronicle); a card's
        # menu item carries the chronicle id it belongs to via e.control.data.
        self.picker_action = "AUDIO"
        self.current_chronicle_id = e.control.data
        await self.pick_file(allowed_extensions=["mp3", "wav", "m4a"])

    async def import_transcript_clicked(self, e):
        self.current_chronicle_id = e.control.data
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

    async def _ask_overwrite_or_append(self) -> str:
        """Modal choice dialog - "overwrite", "append" or "cancel". Flet has no
        built-in await-a-dialog-choice primitive; this is the standard workaround
        (a Future the action buttons resolve, mirroring how ft.FilePicker.pick_files
        itself is implemented under the hood).

        Uses page.show_dialog()/page.pop_dialog() rather than manually appending to
        page.overlay and toggling `open` - AlertDialog's close is animated
        client-side, and show_dialog() wraps on_dismiss so the dialog is only
        actually removed once the client confirms the animation finished (see
        BasePage._wrap_dialog_on_dismiss's own comment: removing it earlier "can drop
        the post-animation dismiss callback entirely"). An earlier version of this
        method called `page.overlay.remove(dialog)` immediately after `open = False`,
        which did exactly that - the buttons worked (the future resolved, the import
        proceeded) but the dialog visually never closed.
        """
        future: asyncio.Future[str] = asyncio.get_event_loop().create_future()

        def choose(choice: str):
            async def handler(e):
                if not future.done():
                    future.set_result(choice)
                self.page.pop_dialog()

            return handler

        dialog = ft.AlertDialog(
            title=ft.Text("Transcript already exists"),
            content=ft.Text(
                "This chronicle already has an imported transcript. Overwrite it "
                "with the new file, or append the new file's lines to the end?"
            ),
            actions=[
                ft.TextButton("Cancel", on_click=choose("cancel")),
                ft.TextButton("Append", on_click=choose("append")),
                ft.FilledButton("Overwrite", on_click=choose("overwrite")),
            ],
        )
        self.page.show_dialog(dialog)
        return await future

    async def _confirm(self, title: str, message: str, confirm_label: str = "Delete") -> bool:
        """Same show_dialog()/pop_dialog() pattern as _ask_overwrite_or_append, for
        the simpler yes/no case."""
        future: asyncio.Future[bool] = asyncio.get_event_loop().create_future()

        def choose(result: bool):
            async def handler(e):
                if not future.done():
                    future.set_result(result)
                self.page.pop_dialog()

            return handler

        dialog = ft.AlertDialog(
            title=ft.Text(title),
            content=ft.Text(message),
            actions=[
                ft.TextButton("Cancel", on_click=choose(False)),
                ft.FilledButton(confirm_label, on_click=choose(True)),
            ],
        )
        self.page.show_dialog(dialog)
        return await future

    async def delete_clicked(self, e):
        chronicle: Chronicle = e.control.data
        confirmed = await self._confirm(
            "Delete chronicle?",
            f"This permanently deletes '{chronicle.title}', its transcript, and any "
            "queued tasks for it. This cannot be undone.",
        )
        if not confirmed:
            return

        await self.chronicle_service.delete_chronicle(chronicle.id)
        self.show_snackbar(f"Deleted '{chronicle.title}'")
        await self.load_chronicles()

    async def handle_file_result(self, file_path):
        try:
            if self.picker_action in ("AUDIO", "TRANSCRIPT"):
                # Title/source_file below intentionally use the *original* name and
                # path (for display) - only the queued file_path needs to be staged.
                original_name = os.path.basename(file_path)
                staged_path = await self.stage_file(file_path)

            if self.picker_action == "AUDIO":
                # Importing a source and transcribing it are separate actions now -
                # this only stores the file; transcription (with a speaker assigned)
                # happens from the Sources panel in the transcript view.
                if self.current_chronicle_id:
                    await self.chronicle_service.add_audio_source(
                        self.current_chronicle_id, staged_path, original_name
                    )
                    self.show_snackbar(f"Added audio source '{original_name}'")
                else:
                    title = original_name.rsplit(".", 1)[0]
                    chronicle = await self.chronicle_service.create_chronicle(title)
                    await self.chronicle_service.add_audio_source(
                        chronicle.id, staged_path, original_name
                    )
                    self.show_snackbar(f"Created '{title}' and added audio source")

            elif self.picker_action == "TRANSCRIPT":
                regex = self.transcript_regex.value
                speaker_group = int(self.transcript_speaker_group.value or 1)
                text_group = int(self.transcript_text_group.value or 2)
                timestamp_group_value = (self.transcript_timestamp_group.value or "").strip()
                timestamp_group = int(timestamp_group_value) if timestamp_group_value else None

                if self.current_chronicle_id:
                    append = False
                    existing_lines = await self.transcript_service.get_transcript(
                        self.current_chronicle_id
                    )
                    if existing_lines:
                        choice = await self._ask_overwrite_or_append()
                        if choice == "cancel":
                            return
                        append = choice == "append"

                    await self.task_service.queue_import(
                        self.current_chronicle_id,
                        staged_path,
                        regex=regex,
                        speaker_group=speaker_group,
                        text_group=text_group,
                        timestamp_group=timestamp_group,
                        append=append,
                    )
                    self.show_snackbar(
                        "Transcript append task queued"
                        if append
                        else "Transcript import task queued"
                    )
                else:
                    title = original_name.rsplit(".", 1)[0]
                    chronicle = await self.chronicle_service.create_chronicle(title)
                    await self.task_service.queue_import(
                        chronicle.id,
                        staged_path,
                        regex=regex,
                        speaker_group=speaker_group,
                        text_group=text_group,
                        timestamp_group=timestamp_group,
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

    async def clean_clicked(self, e):
        chronicle_id = e.control.data
        await self.task_service.queue_clean(chronicle_id)
        self.show_snackbar("Clean task queued")

    async def identify_speakers_clicked(self, e):
        chronicle_id = e.control.data
        count = await self.transcript_service.refresh_speaker_count(chronicle_id)
        self.show_snackbar(f"Found {count} speaker{'s' if count != 1 else ''}")
        await self.load_chronicles()

    def show_snackbar(self, message: str):
        # flet 0.86.4's ft.Page has no `snack_bar` attribute (that was a pre-0.70
        # API) - a SnackBar is a dialog shown through the same stack as ft.AlertDialog.
        self.page.show_dialog(ft.SnackBar(ft.Text(message)))

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

    async def edit_clicked(self, e):
        chronicle: Chronicle = e.control.data
        self.editing_chronicle_id = chronicle.id
        self.edit_title.value = chronicle.title
        self.edit_description.value = chronicle.description or ""
        self.edit_kind.value = "" if chronicle.kind == "Unknown" else chronicle.kind
        self.edit_duration.value = chronicle.duration or ""
        self.edit_dialog.open = True
        self.page.update()

    async def close_edit_dialog(self, e=None):
        self.edit_dialog.open = False
        self.page.update()

    async def save_edit_clicked(self, e):
        chronicle = await self.chronicle_service.get_chronicle(self.editing_chronicle_id)
        if chronicle is None:
            await self.close_edit_dialog()
            self.show_snackbar("Chronicle no longer exists.")
            return

        chronicle.title = self.edit_title.value or chronicle.title
        chronicle.description = self.edit_description.value or None
        chronicle.kind = self.edit_kind.value or "Unknown"
        chronicle.duration = self.edit_duration.value or None
        await self.chronicle_service.update_chronicle(chronicle)

        await self.close_edit_dialog()
        self.show_snackbar("Chronicle updated")
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
            bgcolor=self.colors.card,
            padding=ft.Padding.all(18),
            border=ft.Border.all(1, self.colors.border),
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
                                color=self.colors.muted,
                            ),
                            ft.Text(
                                item.status or "Imported", size=12, color=self.colors.muted
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Text(
                        item.title, size=18, weight=ft.FontWeight.BOLD, color=self.colors.text
                    ),
                    ft.Text(
                        item.description or "No description",
                        max_lines=2,
                        color=self.colors.muted,
                    ),
                    ft.Row(
                        controls=[
                            ft.Text(
                                item.created_at.strftime("%Y-%m-%d"), color=self.colors.muted
                            ),
                            ft.Text(
                                item.duration or "Unknown duration", color=self.colors.muted
                            ),
                            ft.Text(f"{item.speakers_count} speakers", color=self.colors.muted),
                        ],
                        wrap=True,
                        spacing=10,
                    ),
                    ft.Text(tags, color=self.colors.muted),
                    ft.Row(
                        controls=[
                            ft.PopupMenuButton(
                                icon=ft.Icons.UPLOAD_FILE,
                                icon_color=self.colors.muted,
                                items=[
                                    ft.PopupMenuItem(
                                        content=ft.Text("Import Audio"),
                                        icon=ft.Icons.AUDIO_FILE,
                                        data=item.id,
                                        on_click=self.import_audio_clicked,
                                    ),
                                    ft.PopupMenuItem(
                                        content=ft.Text("Import Transcript"),
                                        icon=ft.Icons.DESCRIPTION,
                                        data=item.id,
                                        on_click=self.import_transcript_clicked,
                                    ),
                                ],
                                tooltip="Import to this chronicle",
                            ),
                            ft.IconButton(
                                icon=ft.Icons.EDIT,
                                icon_color=self.colors.muted,
                                data=item,
                                on_click=self.edit_clicked,
                                tooltip="Edit chronicle",
                            ),
                            ft.IconButton(
                                icon=ft.Icons.CLEANING_SERVICES,
                                icon_color=self.colors.muted,
                                data=item.id,
                                on_click=self.clean_clicked,
                                tooltip="Clean transcript",
                            ),
                            ft.IconButton(
                                icon=ft.Icons.RECORD_VOICE_OVER,
                                icon_color=self.colors.muted,
                                data=item.id,
                                on_click=self.identify_speakers_clicked,
                                tooltip="Identify speakers",
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE,
                                icon_color=self.colors.muted,
                                data=item,
                                on_click=self.delete_clicked,
                                tooltip="Delete chronicle",
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                    ),
                ],
            ),
        )
