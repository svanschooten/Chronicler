"""The transcript view's Tags section - a chronicle's tags, added and removed in place."""

import logging
from collections.abc import Callable

import flet as ft

from chronicler.core.models import Chronicle
from chronicler.core.services.chronicle_service import ChronicleService, is_system_tag
from chronicler.desktop.theme import ThemeColors
from chronicler.desktop.widgets import repaint
from chronicler.i18n import t

logger = logging.getLogger(__name__)


class TagsPanel(ft.Column):
    """
    Each tag is a chip with a remove button, and a field below adds one. The chronicle is
    the object the whole view shares, so a change shows in the archive too.
    """

    def __init__(
        self,
        chronicle: Chronicle,
        chronicle_service: ChronicleService,
        colors: ThemeColors,
        show_snackbar: Callable[[str], None],
    ):
        self.chronicle = chronicle
        self.chronicle_service = chronicle_service
        self.colors = colors
        self.show_snackbar = show_snackbar
        self.chips = ft.Row(wrap=True, spacing=6, run_spacing=6)
        self.field = ft.TextField(
            hint_text=t("tags.add"),
            dense=True,
            color=colors.text,
            on_submit=self.add_submitted,
        )
        super().__init__(spacing=6, controls=[self.chips, self.field])
        self.show()

    def show(self) -> None:
        """Draws the chronicle's current tags. The caller repaints."""
        tags = self.chronicle.tags
        self.chips.controls = (
            [
                ft.Chip(
                    label=ft.Text(tag.name, color=self.colors.text),
                    data=tag.name,
                    # A system tag follows the transcript, so it has no remove button.
                    on_delete=None if is_system_tag(tag.name) else self.remove_clicked,
                )
                for tag in tags
            ]
            if tags
            else [ft.Text(t("archive.no_tags"), color=self.colors.muted)]
        )

    async def add_submitted(self, e) -> None:
        name = (e.control.value or "").strip()
        if not name:
            return
        if await self._apply(self.chronicle_service.add_tag(self.chronicle.id, name)):
            self.field.value = ""
            repaint(self.field)

    async def remove_clicked(self, e) -> None:
        await self._apply(self.chronicle_service.remove_tag(self.chronicle.id, e.control.data))

    async def _apply(self, change) -> bool:
        """Awaits a tag change, then shows the tags it left. False if it failed."""
        try:
            updated = await change
        except Exception as error:
            logger.exception(f"Could not change the tags of {self.chronicle.id}")
            self.show_snackbar(t("tags.failed", error=error))
            return False
        self.chronicle.tags = updated.tags
        self.show()
        repaint(self.chips)
        return True
