import logging

import flet as ft

from chronicler.core.services.task_service import TaskService

logger = logging.getLogger(__name__)


class TasksView(ft.Column):
    def __init__(self, task_service: TaskService):
        logger.debug("TasksView constructed")
        self.task_service = task_service
        self.task_list = ft.Column(scroll=ft.ScrollMode.ADAPTIVE, expand=True, spacing=16)
        self.query = ""
        self.hide_completed = False

        super().__init__(
            expand=True,
            spacing=16,
            controls=[
                ft.Text("Processing tasks", size=30, weight=ft.FontWeight.BOLD),
                ft.Text(
                    "Scribes keep work moving, even when you close Chronicler.",
                    color=ft.Colors.GREY_400,
                ),
                ft.Divider(color=ft.Colors.BLUE_GREY_600),
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.SEARCH, color=ft.Colors.GREY_400),
                        ft.TextField(
                            expand=True,
                            hint_text="Search tasks",
                            on_change=self.search_changed,
                        ),
                        ft.Checkbox(
                            label="Hide completed tasks",
                            value=False,
                            on_change=self.hide_completed_changed,
                        ),
                        ft.IconButton(ft.Icons.REFRESH, on_click=self.refresh_clicked),
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
            ft.Colors.AMBER_300 if task.status == TaskStatus.WORKING else ft.Colors.GREY_400
        )
        return ft.Container(
            bgcolor=ft.Colors.BLUE_GREY_700,
            padding=ft.Padding.all(16),
            border=ft.Border.all(1, ft.Colors.BLUE_GREY_600),
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
                            ft.Text(task.type.value, weight=ft.FontWeight.BOLD),
                            ft.Text(f"Status: {task.status}", color=ft.Colors.GREY_400),
                            ft.ProgressBar(value=task.progress / 100.0)
                            if task.status == TaskStatus.WORKING
                            else ft.Container(),
                        ],
                    ),
                    ft.Text(f"{task.progress}%", weight=ft.FontWeight.BOLD),
                ],
            ),
        )
