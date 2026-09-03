"""
The chronicle-level action row shown above a transcript.

Layout only: every operation behind these buttons lives in `desktop/operations.py`,
shared with the archive list. See docs/desktop.md.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import flet as ft

from chronicler.core.models import Chronicle
from chronicler.desktop.operations import ChronicleOperations
from chronicler.desktop.theme import ThemeColors
from chronicler.i18n import t

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChronicleActionCallbacks:
    """What the row asks the view to do once it has changed something."""

    on_changed: Callable[[], Awaitable[None]]
    on_deleted: Callable[[], Awaitable[None]]
    on_summarize: Callable[[], Awaitable[None]]


class ChronicleActions(ft.Row):
    def __init__(
        self,
        chronicle: Chronicle,
        operations: ChronicleOperations,
        colors: ThemeColors,
        callbacks: ChronicleActionCallbacks,
        can_summarize: Callable[[], bool] | None = None,
    ):
        self.chronicle = chronicle
        self.operations = operations
        self.colors = colors
        self.callbacks = callbacks
        self.can_summarize = can_summarize or (lambda: True)

        super().__init__(wrap=True, spacing=4, controls=self._build())

    @property
    def forms(self):
        return self.operations.forms

    def _build(self) -> list[ft.Control]:
        return [
            self._action(ft.Icons.AUDIO_FILE, "actions.import_audio", self.import_audio_clicked),
            self._action(
                ft.Icons.DESCRIPTION, "actions.import_transcript", self.import_transcript_clicked
            ),
            self._action(ft.Icons.CLEANING_SERVICES, "actions.clean", self.clean_clicked),
            self._action(
                ft.Icons.RECORD_VOICE_OVER,
                "actions.identify_speakers",
                self.identify_speakers_clicked,
            ),
            self._action(
                ft.Icons.AUTO_AWESOME,
                "actions.summarize",
                self.summarize_clicked,
                enabled=self.can_summarize(),
                disabled_tooltip="actions.summarize_unavailable",
            ),
            ft.Container(width=8),
            self._action(ft.Icons.EDIT, "actions.edit", self.edit_clicked),
            self._action(ft.Icons.DELETE_OUTLINE, "actions.delete", self.delete_clicked),
        ]

    def _action(
        self,
        icon: ft.IconData,
        key: str,
        on_click,
        enabled: bool = True,
        disabled_tooltip: str | None = None,
    ) -> ft.IconButton:
        return ft.IconButton(
            icon=icon,
            icon_color=self.colors.muted if enabled else self.colors.border,
            tooltip=t(key) if enabled else t(disabled_tooltip or key),
            disabled=not enabled,
            on_click=on_click,
        )

    async def _after(self, changed: bool) -> None:
        if changed:
            await self.callbacks.on_changed()

    async def clean_clicked(self, e):
        await self._after(await self.operations.clean(self.chronicle))

    async def identify_speakers_clicked(self, e):
        await self._after(await self.operations.identify_speakers(self.chronicle))

    async def summarize_clicked(self, e):
        await self.callbacks.on_summarize()

    async def import_audio_clicked(self, e):
        await self._after(await self.operations.import_audio(self.chronicle))

    async def import_transcript_clicked(self, e):
        await self.operations.begin_transcript_import(self.chronicle)

    async def transcript_import_confirmed(self, e=None):
        await self._after(await self.operations.finish_transcript_import())

    async def edit_clicked(self, e):
        await self.operations.begin_edit(self.chronicle)

    async def edit_save_clicked(self, e=None):
        await self._after(await self.operations.finish_edit())

    async def delete_clicked(self, e):
        if await self.operations.delete(self.chronicle):
            await self.callbacks.on_deleted()
