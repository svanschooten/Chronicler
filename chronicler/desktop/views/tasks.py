import logging

import flet as ft

from chronicler.core.services.task_service import TaskService
from chronicler.desktop.theme import theme_colors

logger = logging.getLogger(__name__)


class TasksView(ft.Column):
    def __init__(self, task_service: TaskService, dark_mode: bool = True):
        logger.debug("TasksView constructed")
        self.task_service = task_service
        self.colors = theme_colors(dark_mode)
        self.task_list = ft.Column(scroll=ft.ScrollMode.ADAPTIVE, expand=True, spacing=16)
        self.query = ""
        self.hide_completed = True

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

    async def refresh_clicked(self, e):
        await self.load_tasks()

    async def search_changed(self, e):
        self.query = e.data
        await self.load_tasks()

    async def hide_completed_changed(self, e):
        self.hide_completed = e.control.value
        await self.load_tasks()

    async def load_tasks(self):
        try:
            if self.query:
                tasks = await self.task_service.search_tasks(self.query)
            else:
                tasks = await self.task_service.list_tasks()

            if self.hide_completed:
                tasks = [t for t in tasks if t.status != "DONE"]

            self.task_list.controls = [self.create_task_row(t) for t in tasks]

            if not tasks:
                self.task_list.controls = [ft.Text("No tasks found.")]
            self.update()
        except Exception as e:
            logger.exception(f"Error loading tasks: {e}")
            self.task_list.controls = [ft.Text(f"Error loading tasks: {e}")]
            self.update()

    def create_task_row(self, task) -> ft.Container:
        from chronicler.core.models import TaskStatus

        state_color = (
            self.colors.accent if task.status == TaskStatus.WORKING else self.colors.muted
        )

        # claimed_at/updated_at already exist for claim_next()/update_status() -
        # "started" and "completed" don't need their own columns. updated_at is
        # bumped on every write to the row, so once the task has reached a terminal
        # state it's exactly the completion time.
        timestamp_format = "%Y-%m-%d %H:%M"
        timestamps = [f"Created {task.created_at.strftime(timestamp_format)}"]
        if task.claimed_at:
            timestamps.append(f"Started {task.claimed_at.strftime(timestamp_format)}")
        if task.status in (TaskStatus.DONE, TaskStatus.FAILED):
            timestamps.append(f"Completed {task.updated_at.strftime(timestamp_format)}")

        return ft.Container(
            bgcolor=self.colors.card,
            padding=ft.Padding.all(16),
            border=ft.Border.all(1, self.colors.border),
            border_radius=12,
            content=ft.Row(
                controls=[
                    ft.IconButton(
                        icon=ft.Icons.PENDING_ACTIONS
                        if task.status != TaskStatus.DONE
                        else ft.Icons.CHECK_CIRCLE,
                        icon_color=state_color,
                    ),
                    ft.Column(
                        expand=True,
                        controls=[
                            ft.Text(
                                task.type.value, weight=ft.FontWeight.BOLD, color=self.colors.text
                            ),
                            ft.Text(f"Status: {task.status}", color=self.colors.muted),
                            ft.Text(" · ".join(timestamps), size=12, color=self.colors.muted),
                            ft.ProgressBar(value=task.progress / 100.0)
                            if task.status == TaskStatus.WORKING
                            else ft.Container(),
                        ],
                    ),
                    ft.Text(
                        f"{task.progress}%", weight=ft.FontWeight.BOLD, color=self.colors.text
                    ),
                ],
            ),
        )
