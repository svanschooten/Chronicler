import logging
from uuid import UUID

import flet as ft

from chronicler.core.models import Task, TaskStatus
from chronicler.core.services.chronicle_service import ChronicleService
from chronicler.core.services.task_service import TaskService
from chronicler.desktop.theme import theme_colors

logger = logging.getLogger(__name__)

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M"

RETRYABLE = (TaskStatus.FAILED, TaskStatus.DONE)


class TasksView(ft.Column):
    def __init__(
        self,
        task_service: TaskService,
        chronicle_service: ChronicleService,
        dark_mode: bool = True,
    ):
        logger.debug("TasksView constructed")
        self.task_service = task_service
        self.chronicle_service = chronicle_service
        self.colors = theme_colors(dark_mode)
        self.task_list = ft.Column(scroll=ft.ScrollMode.ADAPTIVE, expand=True, spacing=16)
        self.query = ""
        self.hide_completed = True
        self.chronicle_titles: dict[UUID, str] = {}

        super().__init__(
            expand=True,
            spacing=16,
            controls=[
                ft.Text(
                    "Processing tasks", size=30, weight=ft.FontWeight.BOLD, color=self.colors.text
                ),
                ft.Text(
                    "Scribes keep work moving, even when you close Chronicler.",
                    color=self.colors.muted,
                ),
                ft.Divider(color=self.colors.border),
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.SEARCH, color=self.colors.muted),
                        ft.TextField(
                            expand=True,
                            hint_text="Search tasks",
                            color=self.colors.text,
                            on_change=self.search_changed,
                        ),
                        ft.Checkbox(
                            label="Hide completed tasks",
                            value=True,
                            on_change=self.hide_completed_changed,
                        ),
                        ft.IconButton(
                            ft.Icons.REFRESH,
                            icon_color=self.colors.muted,
                            on_click=self.refresh_clicked,
                        ),
                    ],
                ),
                self.task_list,
            ],
        )

    def did_mount(self):
        logger.debug("TasksView loaded")
        self.page.run_task(self.load_tasks)

    def will_unmount(self):
        logger.debug("TasksView unloaded")

    def show_snackbar(self, message: str):
        self.page.show_dialog(ft.SnackBar(ft.Text(message)))

    async def refresh_clicked(self, e):
        await self.load_tasks()

    async def search_changed(self, e):
        self.query = e.data
        await self.load_tasks()

    async def hide_completed_changed(self, e):
        self.hide_completed = e.control.value
        await self.load_tasks()

    async def retry_clicked(self, e):
        await self.task_service.retry_task(e.control.data)
        self.show_snackbar("Task re-queued")
        await self.load_tasks()

    async def load_tasks(self):
        try:
            if self.query:
                tasks = await self.task_service.search_tasks(self.query)
            else:
                tasks = await self.task_service.list_tasks()

            if self.hide_completed:
                tasks = [t for t in tasks if t.status != TaskStatus.DONE]

            await self._load_chronicle_titles()

            self.task_list.controls = [self.create_task_row(t) for t in tasks] or [
                ft.Text("No tasks found.")
            ]
            self.update()
        except Exception as e:
            logger.exception(f"Error loading tasks: {e}")
            self.task_list.controls = [ft.Text(f"Error loading tasks: {e}")]
            self.update()

    async def _load_chronicle_titles(self) -> None:
        """
        One listing per load rather than a lookup per row - the archive is small, and a
        per-row fetch would be a query per task.
        """
        try:
            chronicles = await self.chronicle_service.list_chronicles()
        except Exception as e:
            logger.warning(f"Could not resolve chronicle titles for the task list: {e}")
            return
        self.chronicle_titles = {c.id: c.title for c in chronicles}

    def _subtitle(self, task: Task) -> str:
        """
        `<chronicle> · <status>`, dropping the chronicle when there isn't one to name -
        a task whose chronicle has since been deleted, or one that isn't chronicle-
        scoped.
        """
        title = self.chronicle_titles.get(task.chronicle_id) if task.chronicle_id else None
        status = f"Status: {task.status.value}"
        return f"{title} · {status}" if title else status

    @staticmethod
    def _timestamps(task: Task) -> str:
        parts = [f"Created {task.created_at.strftime(TIMESTAMP_FORMAT)}"]
        if task.claimed_at:
            parts.append(f"Started {task.claimed_at.strftime(TIMESTAMP_FORMAT)}")
        if task.status in (TaskStatus.DONE, TaskStatus.FAILED):
            parts.append(f"Completed {task.updated_at.strftime(TIMESTAMP_FORMAT)}")
        return " · ".join(parts)

    def create_task_row(self, task: Task) -> ft.Container:
        state_color = self.colors.accent if task.status == TaskStatus.WORKING else self.colors.muted

        details: list[ft.Control] = [
            ft.Text(task.type.value, weight=ft.FontWeight.BOLD, color=self.colors.text),
            ft.Text(self._subtitle(task), color=self.colors.muted),
            ft.Text(self._timestamps(task), size=12, color=self.colors.muted),
        ]
        if task.status == TaskStatus.WORKING:
            details.append(ft.ProgressBar(value=task.progress / 100.0))
        if task.error:
            details.append(ft.Text(task.error, size=12, color=ft.Colors.RED_400, max_lines=3))

        trailing: list[ft.Control] = [
            ft.Text(f"{task.progress}%", weight=ft.FontWeight.BOLD, color=self.colors.text)
        ]
        if task.status in RETRYABLE:
            trailing.append(
                ft.IconButton(
                    icon=ft.Icons.REFRESH,
                    icon_color=self.colors.muted,
                    data=task.id,
                    on_click=self.retry_clicked,
                    tooltip="Run this task again",
                )
            )

        return ft.Container(
            bgcolor=self.colors.card,
            padding=ft.Padding.all(16),
            border=ft.Border.all(1, self.colors.border),
            border_radius=12,
            content=ft.Row(
                controls=[
                    ft.IconButton(
                        icon=self._status_icon(task.status),
                        icon_color=state_color,
                    ),
                    ft.Column(expand=True, controls=details),
                    *trailing,
                ],
            ),
        )

    @staticmethod
    def _status_icon(status: TaskStatus) -> ft.IconData:
        if status == TaskStatus.DONE:
            return ft.Icons.CHECK_CIRCLE
        if status == TaskStatus.FAILED:
            return ft.Icons.ERROR_OUTLINE
        return ft.Icons.PENDING_ACTIONS
