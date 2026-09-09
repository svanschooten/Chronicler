"""The transcript view's Export menu and save flow."""

import logging
from collections.abc import Callable

import flet as ft

from chronicler.core.models import Chronicle
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.desktop.reveal import describe_desktop_integration_error
from chronicler.desktop.widgets import amber_button
from chronicler.i18n import t

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
        self._file_picker = file_picker

    def menu(self) -> ft.PopupMenuButton:
        """The Export dropdown."""
        return ft.PopupMenuButton(
            content=amber_button(t("export.menu"), ft.Icons.FILE_DOWNLOAD, dropdown=True),
            items=[
                ft.PopupMenuItem(
                    content=ft.Text(t("export.plaintext")),
                    icon=ft.Icons.DESCRIPTION,
                    data=False,
                    on_click=self.export_plaintext_clicked,
                ),
                ft.PopupMenuItem(
                    content=ft.Text(t("export.plaintext_timestamps")),
                    icon=ft.Icons.SCHEDULE,
                    data=True,
                    on_click=self.export_plaintext_clicked,
                ),
                ft.PopupMenuItem(
                    content=ft.Text(t("export.srt")),
                    icon=ft.Icons.SUBTITLES,
                    on_click=self.export_srt_clicked,
                ),
                ft.PopupMenuItem(
                    content=ft.Text(t("export.html")),
                    icon=ft.Icons.HTML,
                    on_click=self.export_html_clicked,
                ),
                ft.PopupMenuItem(
                    content=ft.Text(t("export.pdf")),
                    icon=ft.Icons.PICTURE_AS_PDF,
                    on_click=self.export_pdf_clicked,
                ),
                ft.PopupMenuItem(
                    content=ft.Text(t("export.zip")),
                    icon=ft.Icons.FOLDER_ZIP,
                    disabled=True,
                ),
            ],
            tooltip=t("export.tooltip"),
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

    async def export_srt_clicked(self, e):
        try:
            content = await self.transcript_service.export_srt(self.chronicle.id)
        except Exception as ex:
            logger.error(f"Error exporting subtitles: {ex}")
            self.show_snackbar(t("export.failed", error=ex))
            return

        await self._save(content, f"{self.default_file_stem()}.srt", "srt")

    async def export_html_clicked(self, e):
        try:
            content = await self.transcript_service.export_html(self.chronicle.id, self.chronicle.title)
        except Exception as ex:
            logger.error(f"Error exporting html: {ex}")
            self.show_snackbar(t("export.failed", error=ex))
            return

        await self._save(content, f"{self.default_file_stem()}.html", "html")

    async def export_pdf_clicked(self, e):
        try:
            content = await self.transcript_service.export_pdf(self.chronicle.id, self.chronicle.title)
        except Exception as ex:
            logger.error(f"Error exporting pdf: {ex}")
            self.show_snackbar(t("export.failed", error=ex))
            return

        await self._save(content, f"{self.default_file_stem()}.pdf", "pdf", True)

    async def _save(self, content: str|bytearray, file_name: str, extension: str, write_bytes: bool = False) -> None:
        picker = self._file_picker()
        if picker is None:
            self.show_snackbar(t("export.no_picker"))
            return

        try:
            destination = await picker.save_file(
                dialog_title=t("export.tooltip"),
                file_name=file_name,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=[extension],
            )
        except Exception as ex:
            logger.error(f"Error opening the save dialog: {ex}")
            self.show_snackbar(describe_desktop_integration_error(ex))
            return
        if not destination:
            return

        try:
            if write_bytes:
                with open(destination, "wb") as handle:
                    handle.write(content)
            else:
                with open(destination, "w", encoding="utf-8") as handle:
                    handle.write(content)
        except OSError as ex:
            logger.error(f"Error writing export file: {ex}")
            self.show_snackbar(t("export.write_failed", error=ex))
            return

        self.show_snackbar(t("export.saved", path=destination))

    def default_file_stem(self) -> str:
        """The chronicle title reduced to something safe to suggest as a filename."""
        safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in self.chronicle.title)
        return safe or "transcript"
