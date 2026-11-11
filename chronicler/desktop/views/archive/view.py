import asyncio
import logging
from collections.abc import Awaitable, Callable

import flet as ft

from chronicler.core.models import Chronicle
from chronicler.core.services.chronicle_service import ChronicleService
from chronicler.core.services.task_service import TaskService
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.desktop.forms import CreateChronicleForm
from chronicler.desktop.imports import ImportCoordinator
from chronicler.desktop.operations import ChronicleOperations
from chronicler.desktop.picking import FilePickerFlow
from chronicler.desktop.theme import theme_colors
from chronicler.desktop.views.archive.cards import (
    ChronicleCardHandlers,
    chronicle_card,
    transcript_match_card,
)
from chronicler.desktop.widgets import amber_button
from chronicler.i18n import t

logger = logging.getLogger(__name__)

# Typing pauses this long before the transcript search starts, so one is not started per
# keystroke. The search opens every chronicle. See docs/search.md.
TRANSCRIPT_SEARCH_DELAY = 0.3
# A refresh after a finished task waits longer, so tasks finishing one after another start
# one transcript search between them rather than one each.
REFRESH_SEARCH_DELAY = 2.0


class ArchiveView(ft.Column):
    def __init__(
        self,
        chronicle_service: ChronicleService,
        task_service: TaskService,
        on_open_chronicle: Callable[[Chronicle], Awaitable[None]],
        stage_file: Callable[[str], Awaitable[str]],
        transcript_service: TranscriptService,
        dark_mode: bool = True,
        can_link: bool = True,
    ):
        logger.debug("ArchiveView constructed")
        self.chronicle_service = chronicle_service
        self.task_service = task_service
        self.transcript_service = transcript_service
        self.on_open_chronicle = on_open_chronicle
        self.colors = theme_colors(dark_mode)
        self.can_link = can_link
        self.query = ""
        # Bumped by every load; a transcript search finishing for an older one is dropped.
        self._generation = 0
        # The "Said in" section last shown, and for which query. It stays on screen while
        # the same query is searched again, so a refresh does not make it blink away.
        self._transcript_section: list[ft.Control] = []
        self._section_query = ""
        self.file_picker: ft.FilePicker | None = None
        self.picker = FilePickerFlow(lambda: self.file_picker, self.show_snackbar)

        self.chronicle_list = ft.Column(spacing=12, scroll=ft.ScrollMode.ADAPTIVE, expand=True)

        self.create_form = CreateChronicleForm(
            on_cancel=self.close_create_dialog, on_create=self.create_chronicle_clicked
        )
        self.operations = ChronicleOperations(
            ImportCoordinator(chronicle_service, task_service, transcript_service, stage_file),
            task_service,
            transcript_service,
            chronicle_service,
            self.picker,
            self.show_snackbar,
            lambda: self.page,
            on_changed=self.load_chronicles,
        )

        super().__init__(expand=True, spacing=16, controls=self._build_controls())

    def _link_items(self) -> list[ft.PopupMenuItem]:
        """Link names a file on this machine, which a thin client's server cannot see."""
        if not self.can_link:
            return []
        return [
            ft.PopupMenuItem(
                content=ft.Text(t("archive.link")),
                icon=ft.Icons.LINK,
                on_click=self.link_chronicle_clicked,
            )
        ]

    def _build_controls(self) -> list[ft.Control]:
        return [
            ft.Row(
                controls=[
                    ft.Column(
                        controls=[
                            ft.Text(
                                t("archive.title"),
                                size=30,
                                weight=ft.FontWeight.BOLD,
                                color=self.colors.text,
                            ),
                            ft.Text(t("archive.subtitle"), color=self.colors.muted),
                        ],
                    ),
                    ft.PopupMenuButton(
                        content=amber_button(t("archive.import"), ft.Icons.ADD, dropdown=True),
                        items=[
                            ft.PopupMenuItem(
                                content=ft.Text(t("actions.import_audio")),
                                icon=ft.Icons.AUDIO_FILE,
                                on_click=self.import_audio_clicked,
                            ),
                            ft.PopupMenuItem(
                                content=ft.Text(t("actions.import_transcript")),
                                icon=ft.Icons.DESCRIPTION,
                                on_click=self.import_transcript_clicked,
                            ),
                            *self._link_items(),
                        ],
                    ),
                    amber_button(t("archive.new"), ft.Icons.ADD, on_click=self.show_create_dialog),
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
                        hint_text=t("archive.search"),
                        color=self.colors.text,
                        on_change=self.search_changed,
                    ),
                ],
            ),
            self.chronicle_list,
        ]

    @property
    def _forms(self) -> list:
        return [self.create_form, *self.operations.forms]

    def did_mount(self):
        logger.debug("ArchiveView loaded")
        self.page.run_task(self.mount_async)

    async def mount_async(self):
        logger.debug("ArchiveView.mount_async started")
        if self.file_picker is None:
            self.file_picker = ft.FilePicker()
        if self.file_picker not in self.page.services:
            self.page.services.append(self.file_picker)

        for form in self._forms:
            form.attach(self.page)

        self.page.update()
        await self.load_chronicles()
        logger.debug("ArchiveView.mount_async finished")

    def will_unmount(self):
        logger.debug("ArchiveView unloaded")
        for form in self._forms:
            form.detach(self.page)
        if self.file_picker and self.file_picker in self.page.services:
            self.page.services.remove(self.file_picker)
        self.page.update()

    def show_snackbar(self, message: str):
        self.page.show_dialog(ft.SnackBar(ft.Text(message)))

    async def refresh(self) -> None:
        """Re-reads the list after a task finished, keeping the search and any open form."""
        await self.load_chronicles(transcript_delay=REFRESH_SEARCH_DELAY)

    async def refresh_clicked(self, e):
        await self.load_chronicles()

    async def search_changed(self, e):
        self.query = e.data
        await self.load_chronicles(transcript_delay=TRANSCRIPT_SEARCH_DELAY)

    async def load_chronicles(self, transcript_delay: float = 0.0):
        """
        The chronicles whose title, description or tags match, then, below them and once
        it finishes, the ones whose transcripts do.
        """
        self._generation += 1
        generation = self._generation
        try:
            if self.query:
                chronicles = await self.chronicle_service.search_chronicles(self.query)
            else:
                chronicles = await self.chronicle_service.list_chronicles()
        except Exception as e:
            logger.exception(f"Error loading chronicles: {e}")
            self.chronicle_list.controls = [ft.Text(t("archive.load_failed", error=e))]
            self.update()
            return

        cards: list[ft.Control] = [self.create_chronicle_card(c) for c in chronicles]
        if self._section_query != self.query or not self.query.strip():
            self._transcript_section, self._section_query = [], ""
        self._show(cards, self._transcript_section)

        if self.query.strip():
            await self._add_transcript_matches(generation, transcript_delay, cards, chronicles)

    def _show(self, cards: list[ft.Control], section: list[ft.Control]) -> None:
        """The cards found by title, then the "Said in" section, or the empty message."""
        controls = [*cards, *section]
        self.chronicle_list.controls = controls or [ft.Text(t("archive.empty"))]
        self.update()

    async def _add_transcript_matches(
        self,
        generation: int,
        delay: float,
        cards: list[ft.Control],
        found_by_title: list[Chronicle],
    ) -> None:
        """Shows the transcript matches below `cards`, unless a newer load started meanwhile."""
        if delay:
            await asyncio.sleep(delay)
            if generation != self._generation:
                return
        query = self.query
        failed: Exception | None = None
        try:
            matches = await self.transcript_service.search_transcripts(query)
        except Exception as error:
            logger.exception(f"Error searching transcripts: {error}")
            matches, failed = [], error
        if generation != self._generation:
            return

        # A chronicle already listed by its title is not listed a second time.
        shown = {chronicle.id for chronicle in found_by_title}
        matches = [match for match in matches if match.chronicle.id not in shown]

        section: list[ft.Control] = []
        if failed is not None:
            section = [ft.Text(t("archive.transcript_search_failed", error=failed))]
        elif matches:
            section = [
                ft.Text(
                    t("archive.in_transcripts"),
                    size=16,
                    weight=ft.FontWeight.BOLD,
                    color=self.colors.text,
                ),
                *[
                    transcript_match_card(match, self.colors, self.open_chronicle_clicked)
                    for match in matches
                ],
            ]
        self._transcript_section, self._section_query = section, query
        self._show(cards, section)

    def create_chronicle_card(self, item: Chronicle) -> ft.Container:
        return chronicle_card(
            item,
            self.colors,
            ChronicleCardHandlers(
                on_open=self.open_chronicle_clicked,
                on_import_audio=self.import_audio_clicked,
                on_import_transcript=self.import_transcript_clicked,
                on_edit=self.edit_clicked,
                on_clean=self.clean_clicked,
                on_identify_speakers=self.identify_speakers_clicked,
                on_delete=self.delete_clicked,
            ),
        )

    async def open_chronicle_clicked(self, e):
        await self.on_open_chronicle(e.control.data)

    async def show_create_dialog(self, e):
        self.create_form.open(self.page)

    async def close_create_dialog(self, e=None):
        self.create_form.close(self.page)

    async def create_chronicle_clicked(self, e):
        title = self.create_form.title
        if not title:
            return
        await self.chronicle_service.create_chronicle(title)
        self.create_form.clear()
        await self.close_create_dialog()
        await self.load_chronicles()

    async def edit_clicked(self, e):
        await self.operations.begin_edit(e.control.data)

    async def delete_clicked(self, e):
        if await self.operations.delete(e.control.data):
            await self.load_chronicles()

    async def clean_clicked(self, e):
        await self.operations.clean(e.control.data)

    async def identify_speakers_clicked(self, e):
        if await self.operations.identify_speakers(e.control.data):
            await self.load_chronicles()

    async def import_audio_clicked(self, e):
        if await self.operations.import_audio(e.control.data):
            await self.load_chronicles()

    async def import_transcript_clicked(self, e):
        await self.operations.begin_transcript_import(e.control.data)

    async def link_chronicle_clicked(self, e):
        if await self.operations.link_chronicle():
            await self.load_chronicles()
