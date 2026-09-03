"""The transcript view's Summaries panel - generated recaps, numbered so they compare."""

import logging
from collections.abc import Callable

import flet as ft

from chronicler.core.models import Chronicle, Summary
from chronicler.core.services.task_service import TaskService
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.desktop.dialogs import await_dialog, confirm
from chronicler.desktop.theme import ThemeColors
from chronicler.i18n import t

logger = logging.getLogger(__name__)


class SummariesPanel(ft.Column):
    def __init__(
        self,
        chronicle: Chronicle,
        transcript_service: TranscriptService,
        task_service: TaskService,
        colors: ThemeColors,
        show_snackbar: Callable[[str], None],
        available_models: Callable[[], list[str]] | None = None,
    ):
        self.chronicle = chronicle
        self.transcript_service = transcript_service
        self.task_service = task_service
        self.colors = colors
        self.show_snackbar = show_snackbar
        self.available_models = available_models or (lambda: [])
        self.summaries: list[Summary] = []

        self.summary_list = ft.Column(spacing=4)
        super().__init__(
            tight=True,
            controls=[
                ft.Row(
                    controls=[
                        ft.Text(t("summaries.title"), weight=ft.FontWeight.BOLD, color=colors.text),
                        ft.IconButton(
                            icon=ft.Icons.AUTO_AWESOME,
                            icon_color=colors.muted,
                            icon_size=16,
                            tooltip=t("summaries.generate"),
                            on_click=self.generate_clicked,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                self.summary_list,
            ],
        )

    async def load(self):
        try:
            self.summaries = await self.transcript_service.list_summaries(self.chronicle.id)
        except Exception as error:
            logger.exception(f"Error loading summaries: {error}")
            self.summaries = []

        self.summary_list.controls = (
            [self._row(summary) for summary in self.summaries]
            if self.summaries
            else [ft.Text(t("summaries.empty"), size=12, color=self.colors.muted)]
        )
        self.summary_list.update()

    def _row(self, summary: Summary) -> ft.Row:
        subtitle = summary.model or t("common.unknown")
        return ft.Row(
            controls=[
                ft.Column(
                    expand=True,
                    spacing=0,
                    controls=[
                        ft.Text(
                            f"{summary.number}. {summary.title or t('summaries.untitled')}",
                            size=12,
                            color=self.colors.text,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Text(subtitle, size=10, color=self.colors.muted),
                    ],
                ),
                ft.IconButton(
                    icon=ft.Icons.VISIBILITY,
                    icon_size=16,
                    icon_color=self.colors.muted,
                    data=str(summary.id),
                    on_click=self.read_clicked,
                    tooltip=t("summaries.read"),
                ),
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    icon_size=16,
                    icon_color=self.colors.muted,
                    data=str(summary.id),
                    on_click=self.delete_clicked,
                    tooltip=t("common.delete"),
                ),
            ],
        )

    async def read_clicked(self, e):
        summary = self._find(e.control.data)
        if summary is None:
            return
        await self._show_text(
            f"{summary.number}. {summary.title or t('summaries.untitled')}", summary.content
        )

    async def delete_clicked(self, e):
        summary = self._find(e.control.data)
        if summary is None:
            return
        if not await confirm(
            self.page,
            t("summaries.delete_title"),
            t("summaries.delete_message", number=summary.number),
        ):
            return
        await self.transcript_service.delete_summary(self.chronicle.id, summary.id)
        await self.load()

    async def generate_clicked(self, e):
        models = self.available_models()
        chosen = await self._ask_options(models)
        if chosen is None:
            return

        await self.task_service.queue_summarize(
            self.chronicle.id,
            model=chosen.get("model") or None,
            title=chosen.get("title") or None,
            recap_prompt=chosen.get("prompt") or None,
        )
        self.show_snackbar(t("summaries.queued"))

    def _find(self, summary_id: str) -> Summary | None:
        return next((s for s in self.summaries if str(s.id) == summary_id), None)

    async def _show_text(self, title: str, body: str) -> None:
        def build(on_choice) -> ft.AlertDialog:
            return ft.AlertDialog(
                title=ft.Text(title),
                content=ft.Container(
                    width=680,
                    height=460,
                    content=ft.Column(
                        scroll=ft.ScrollMode.AUTO,
                        controls=[ft.Text(body, selectable=True, color=self.colors.text)],
                    ),
                ),
                actions=[ft.TextButton(t("common.close"), on_click=on_choice(lambda: None))],
            )

        await await_dialog(self.page, build)

    async def _ask_options(self, models: list[str]) -> dict | None:
        model_field = ft.Dropdown(
            label=t("summaries.model"),
            value=models[0] if models else None,
            options=[ft.DropdownOption(key=name, text=name) for name in models],
            editable=True,
            enable_filter=True,
        )
        title_field = ft.TextField(label=t("summaries.name"))
        prompt_field = ft.TextField(
            label=t("summaries.prompt"),
            multiline=True,
            max_lines=5,
            hint_text=t("summaries.prompt_hint"),
        )

        def build(on_choice) -> ft.AlertDialog:
            return ft.AlertDialog(
                title=ft.Text(t("summaries.generate")),
                content=ft.Column(
                    [
                        ft.Text(t("summaries.generate_message")),
                        model_field,
                        title_field,
                        prompt_field,
                    ],
                    tight=True,
                    width=460,
                ),
                actions=[
                    ft.TextButton(t("common.cancel"), on_click=on_choice(lambda: None)),
                    ft.FilledButton(
                        t("summaries.generate_action"),
                        on_click=on_choice(
                            lambda: {
                                "model": model_field.value,
                                "title": title_field.value,
                                "prompt": prompt_field.value,
                            }
                        ),
                    ),
                ],
            )

        return await await_dialog(self.page, build)
