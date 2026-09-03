"""
The archive view's form dialogs - create a chronicle, edit its metadata, and configure a
transcript import.
"""

import flet as ft

from chronicler.core.models import Chronicle
from chronicler.desktop.imports import TranscriptImportOptions
from chronicler.i18n import t


class OverlayForm:
    """Shared plumbing for a form dialog kept in `page.overlay`."""

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
        self.title_field = ft.TextField(label=t("forms.chronicle_title"))
        super().__init__(
            ft.AlertDialog(
                title=ft.Text(t("forms.create_title")),
                content=self.title_field,
                actions=[
                    ft.TextButton(t("common.cancel"), on_click=on_cancel),
                    ft.TextButton(t("forms.create"), on_click=on_create),
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
        self.title_field = ft.TextField(label=t("forms.title"))
        self.description_field = ft.TextField(label=t("forms.description"), multiline=True)
        self.kind_field = ft.TextField(label=t("forms.kind"), hint_text=t("forms.kind_hint"))
        self.duration_field = ft.TextField(
            label=t("forms.duration"), hint_text=t("forms.duration_hint")
        )
        super().__init__(
            ft.AlertDialog(
                title=ft.Text(t("forms.edit_title")),
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
                    ft.TextButton(t("common.cancel"), on_click=on_cancel),
                    ft.TextButton(t("common.save"), on_click=on_save),
                ],
            )
        )

    def fill_from(self, chronicle: Chronicle) -> None:
        self.title_field.value = chronicle.title
        self.description_field.value = chronicle.description or ""
        self.kind_field.value = "" if chronicle.kind == "Unknown" else chronicle.kind
        self.duration_field.value = chronicle.duration or ""

    def apply_to(self, chronicle: Chronicle) -> Chronicle:
        """
        Writes the field values back onto `chronicle`, keeping its existing title if the
        field was blanked (a chronicle with no title at all isn't useful) and restoring
        the "Unknown"/None defaults for the optional fields.
        """
        chronicle.title = self.title_field.value or chronicle.title
        chronicle.description = self.description_field.value or None
        chronicle.kind = self.kind_field.value or "Unknown"
        chronicle.duration = self.duration_field.value or None
        return chronicle


class TranscriptImportForm(OverlayForm):
    def __init__(self, on_cancel, on_import):
        self.regex_field = ft.TextField(
            label=t("forms.regex"),
            value=r"^([A-Za-z0-9 _]+)\s*:(.*)$",
            hint_text=t("forms.regex_hint"),
        )
        self.speaker_group_field = ft.TextField(label=t("forms.speaker_group"), value="1")
        self.text_group_field = ft.TextField(label=t("forms.text_group"), value="2")
        self.timestamp_group_field = ft.TextField(
            label=t("forms.timestamp_group"),
            hint_text=t("forms.timestamp_group_hint"),
        )
        super().__init__(
            ft.AlertDialog(
                title=ft.Text(t("actions.import_transcript")),
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
                    ft.TextButton(t("common.cancel"), on_click=on_cancel),
                    ft.TextButton(t("forms.select_and_import"), on_click=on_import),
                ],
            )
        )

    def options(self) -> TranscriptImportOptions:
        """The fields as the coordinator wants them."""
        timestamp_value = (self.timestamp_group_field.value or "").strip()
        return TranscriptImportOptions(
            regex=self.regex_field.value,
            speaker_group=int(self.speaker_group_field.value or 1),
            text_group=int(self.text_group_field.value or 2),
            timestamp_group=int(timestamp_value) if timestamp_value else None,
        )
