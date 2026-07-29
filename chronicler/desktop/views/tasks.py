import logging

import flet as ft

from chronicler.core.services.task_service import TaskService

logger = logging.getLogger(__name__)


class TasksView(ft.Column):
    def __init__(self, task_service: TaskService):
        logger.debug("TasksView constructed")
        self.task_service = task_service
        self.task_list = ft.Column(scroll=ft.ScrollMode.ADAPTIVE, expand=True)

        super().__init__(
            controls=[
                ft.Row(
                    [
                        ft.Text("Tasks", theme_style=ft.TextThemeStyle.HEADLINE_MEDIUM),
                        ft.IconButton(ft.Icons.REFRESH, on_click=self.refresh_clicked),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Divider(),
                self.task_list,
            ],
            expand=True,
        )

    def did_mount(self):
        logger.debug("TasksView loaded")
        self.page.run_task(self.load_tasks)

    def will_unmount(self):
        logger.debug("TasksView unloaded")

    async def refresh_clicked(self, e):
        await self.load_tasks()

    async def load_tasks(self):
        try:
            tasks = await self.task_service.list_tasks()
            self.task_list.controls = []
            for t in tasks:
                subtitle = ft.Column(
                    [
                        ft.Text(f"Status: {t.status}"),
                        ft.ProgressBar(value=t.progress / 100.0, width=200)
                        if t.status == "WORKING"
                        else ft.Container(),
                    ]
                )

                self.task_list.controls.append(
                    ft.ListTile(
                        title=ft.Text(f"{t.type.value} Task"),
                        subtitle=subtitle,
                        leading=ft.Icon(ft.Icons.TASK_ALT),
                        trailing=ft.Text(f"{t.progress}%") if t.progress > 0 else None,
                    )
                )

            if not tasks:
                self.task_list.controls = [ft.Text("No tasks found.")]
            self.update()
        except Exception as e:
            logger.exception(f"Error loading tasks: {e}")
            self.task_list.controls = [ft.Text(f"Error loading tasks: {e}")]
            self.update()
