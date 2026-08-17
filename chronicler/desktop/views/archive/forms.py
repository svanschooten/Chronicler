"""The archive view's form dialogs - create a chronicle, edit its metadata, and
configure a transcript import.

Unlike the one-shot question dialogs in `chronicler.desktop.dialogs`, these are
long-lived: each owns input fields whose values are read back after the user clicks
an action, so they're built once with the view and hosted in `page.overlay` for as
long as it's mounted. Wrapping each in a small object keeps that field/dialog/parse
grouping in one place instead of spreading a dozen loose attributes (and their
int-parsing) across ArchiveView.
"""

import flet as ft

from chronicler.core.models import Chronicle
from chronicler.desktop.views.archive.imports import TranscriptImportOptions


class OverlayForm:
    """Shared plumbing for a form dialog kept in `page.overlay`.

    These use the `overlay` + `open` flag route rather than
    `page.show_dialog()`/`pop_dialog()`, because they need to exist (and hold their
    field values) before and after being shown, not just for the duration of one
    await. `attach`/`detach` are idempotent so a view's mount/unmount can call them
    without tracking whether it already did.
    """

    def __init__(self, dialog: ft.AlertDialog):
        self.dialog = dialog

    def attach(self, page: ft.Page) -> None:
        if self.dialog not in page.overlay:
            page.overlay.append(self.dialog)

    def detach(self, page: ft.Page) -> None:
        if self.dialog in page.overlay:
            page.overlay.remove(self.dialog)

    def open(self, page: ft.Page) -> None:
        self.dialog.open = True
        page.update()

    def close(self, page: ft.Page) -> None:
        self.dialog.open = False
        page.update()


class CreateChronicleForm(OverlayForm):
    def __init__(self, on_cancel, on_create):
        self.title_field = ft.TextField(label="Chronicle Title")
        super().__init__(
            ft.AlertDialog(
                title=ft.Text("Create New Chronicle"),
                content=self.title_field,
                actions=[
                    ft.TextButton("Cancel", on_click=on_cancel),
                    ft.TextButton("Create", on_click=on_create),
                ],
            )
        )

    @property
    def title(self) -> str | None:
        return self.title_field.value

    def clear(self) -> None:
        self.title_field.value = ""


class EditChronicleForm(OverlayForm):
    def __init__(self, on_cancel, on_save):
        self.title_field = ft.TextField(label="Title")
        self.description_field = ft.TextField(label="Description", multiline=True)
        self.kind_field = ft.TextField(
            label="Kind", hint_text="e.g. Podcast, D&D session, Meeting"
        )
        self.duration_field = ft.TextField(label="Duration", hint_text="e.g. 1h 24m")
        super().__init__(
            ft.AlertDialog(
                title=ft.Text("Edit Chronicle"),
                content=ft.Column(
                    [
                        self.title_field,
                        self.description_field,
                        self.kind_field,
                        self.duration_field,
                    ],
                    tight=True,
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=on_cancel),
                    ft.TextButton("Save", on_click=on_save),
                ],
            )
        )

    def fill_from(self, chronicle: Chronicle) -> None:
        self.title_field.value = chronicle.title
        self.description_field.value = chronicle.description or ""
        # "Unknown" is the model default, not something the user typed - start blank
        # rather than round-tripping the placeholder as if it were real data.
        self.kind_field.value = "" if chronicle.kind == "Unknown" else chronicle.kind
        self.duration_field.value = chronicle.duration or ""

    def apply_to(self, chronicle: Chronicle) -> Chronicle:
        """Writes the field values back onto `chronicle`, keeping its existing title
        if the field was blanked (a chronicle with no title at all isn't useful) and
        restoring the "Unknown"/None defaults for the optional fields."""
        chronicle.title = self.title_field.value or chronicle.title
        chronicle.description = self.description_field.value or None
        chronicle.kind = self.kind_field.value or "Unknown"
        chronicle.duration = self.duration_field.value or None
        return chronicle


class TranscriptImportForm(OverlayForm):
    def __init__(self, on_cancel, on_import):
        self.regex_field = ft.TextField(
            label="Line Regex",
            value=r"^([A-Za-z0-9 _]+)\s*:(.*)$",
            hint_text=r"e.g. ^([A-Z]+):\s+(.*)$",
        )
        self.speaker_group_field = ft.TextField(label="Speaker Group Index", value="1")
        self.text_group_field = ft.TextField(label="Text Group Index", value="2")
        self.timestamp_group_field = ft.TextField(
            label="Timestamp Group Index (optional)",
            hint_text="e.g. 3 for ^([A-Za-z]+):\\s*(.*)\\s+\\[(\\d\\d:\\d\\d:\\d\\d)\\]$ - "
            "leave blank for no timestamps",
        )
        super().__init__(
            ft.AlertDialog(
                title=ft.Text("Import Transcript"),
                content=ft.Column(
                    [
                        self.regex_field,
                        self.speaker_group_field,
                        self.text_group_field,
                        self.timestamp_group_field,
                    ],
                    tight=True,
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=on_cancel),
                    ft.TextButton("Select File & Import", on_click=on_import),
                ],
            )
        )

    def options(self) -> TranscriptImportOptions:
        """The fields as the coordinator wants them. A blank timestamp field means
        "no timestamps" rather than group 0, so it stays None."""
        timestamp_value = (self.timestamp_group_field.value or "").strip()
        return TranscriptImportOptions(
            regex=self.regex_field.value,
            speaker_group=int(self.speaker_group_field.value or 1),
            text_group=int(self.text_group_field.value or 2),
            timestamp_group=int(timestamp_value) if timestamp_value else None,
        )
