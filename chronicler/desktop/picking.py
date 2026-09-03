"""Opening a native file dialog, in the one place that knows how it can fail."""

import logging
from collections.abc import Callable

import flet as ft

from chronicler.desktop.reveal import describe_desktop_integration_error
from chronicler.i18n import t

logger = logging.getLogger(__name__)


class FilePickerFlow:
    """
    A picker call plus the error handling every caller needs.

    The picker is fetched through a callable rather than held: views register theirs in
    `page.services` on mount, so it does not exist yet when they are constructed.
    """

    def __init__(
        self,
        get_picker: Callable[[], ft.FilePicker | None],
        show_snackbar: Callable[[str], None],
    ):
        self.get_picker = get_picker
        self.show_snackbar = show_snackbar

    async def pick_file(self, allowed_extensions: list[str] | None = None) -> str | None:
        """The chosen file's path, or None if the user cancelled or the dialog failed."""
        picker = self._picker()
        if picker is None:
            return None

        try:
            result = await picker.pick_files(
                allowed_extensions=allowed_extensions,
                file_type=ft.FilePickerFileType.CUSTOM
                if allowed_extensions
                else ft.FilePickerFileType.ANY,
            )
        except Exception as error:
            self._failed(error)
            return None

        return result[0].path if result else None

    async def pick_directory(self, dialog_title: str) -> str | None:
        picker = self._picker()
        if picker is None:
            return None

        try:
            chosen = await picker.get_directory_path(dialog_title=dialog_title)
        except Exception as error:
            self._failed(error)
            return None

        return chosen or None

    def _picker(self) -> ft.FilePicker | None:
        picker = self.get_picker()
        if picker is None:
            self.show_snackbar(t("export.no_picker"))
        return picker

    def _failed(self, error: Exception) -> None:
        logger.error(f"The file dialog could not be opened: {error}")
        self.show_snackbar(describe_desktop_integration_error(error))
