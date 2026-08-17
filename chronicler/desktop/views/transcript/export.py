"""The transcript view's Export menu and save flow.

Split from the view because exporting is a self-contained errand - pick a format,
ask the service to render it, ask the user where to put it, write the file - that
happens to need none of the view's state beyond the chronicle it belongs to.
"""

import logging
from collections.abc import Callable

import flet as ft

from chronicler.core.models import Chronicle
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.desktop.widgets import amber_button

logger = logging.getLogger(__name__)


class TranscriptExporter:
    def __init__(
        self,
        chronicle: Chronicle,
        transcript_service: TranscriptService,
        show_snackbar: Callable[[str], None],
        file_picker: Callable[[], ft.FilePicker | None],
    ):
        self.chronicle = chronicle
        self.transcript_service = transcript_service
        self.show_snackbar = show_snackbar
        # A getter, not the picker itself: the view only creates its FilePicker once
        # it's mounted (a Service has to be registered on a live page), which is after
        # this object is built.
        self._file_picker = file_picker

    def menu(self) -> ft.PopupMenuButton:
        """The Export dropdown. The disabled entries are deliberate signposting of
        formats that are planned but not built yet (see TODO.md, Phase 6) rather than
        silently offering only plain text."""
        return ft.PopupMenuButton(
            content=amber_button("Export", ft.Icons.FILE_DOWNLOAD, dropdown=True),
            items=[
                ft.PopupMenuItem(
                    content=ft.Text("Plain text (.txt)"),
                    icon=ft.Icons.DESCRIPTION,
                    data=False,
                    on_click=self.export_plaintext_clicked,
                ),
                ft.PopupMenuItem(
                    content=ft.Text("Plain text with timestamps (.txt)"),
                    icon=ft.Icons.SCHEDULE,
                    data=True,
                    on_click=self.export_plaintext_clicked,
                ),
                ft.PopupMenuItem(
                    content=ft.Text("HTML (coming soon)"), icon=ft.Icons.HTML, disabled=True
                ),
                ft.PopupMenuItem(
                    content=ft.Text("PDF (coming soon)"),
                    icon=ft.Icons.PICTURE_AS_PDF,
                    disabled=True,
                ),
                ft.PopupMenuItem(
                    content=ft.Text("Chronicle .zip (coming soon)"),
                    icon=ft.Icons.FOLDER_ZIP,
                    disabled=True,
                ),
            ],
            tooltip="Export transcript",
        )

    async def export_plaintext_clicked(self, e):
        include_timestamps = bool(e.control.data)
        try:
            content = await self.transcript_service.export_plaintext(
                self.chronicle.id, include_timestamps=include_timestamps
            )
        except Exception as ex:
            logger.error(f"Error exporting transcript: {ex}")
            self.show_snackbar(f"Error exporting transcript: {ex}")
            return

        picker = self._file_picker()
        if picker is None:
            self.show_snackbar("File picker not available.")
            return

        suffix = "_timestamps" if include_timestamps else ""
        destination = await picker.save_file(
            dialog_title="Export transcript as plain text",
            file_name=f"{self.default_file_stem()}{suffix}.txt",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["txt"],
        )
        if not destination:
            return

        try:
            with open(destination, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as ex:
            logger.error(f"Error writing export file: {ex}")
            self.show_snackbar(f"Error writing export file: {ex}")
            return

        self.show_snackbar(f"Exported to {destination}")

    def default_file_stem(self) -> str:
        """The chronicle title reduced to something safe to suggest as a filename.
        Falls back to "transcript" when the title has no usable characters at all."""
        safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in self.chronicle.title)
        return safe or "transcript"
