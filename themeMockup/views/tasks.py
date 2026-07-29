import flet as ft

from models import TASKS


def TasksView(
    query: str,
    on_query_change: Callable[[str], None],
    dark_mode: bool,
    hide_completed: bool,
    on_hide_processed_change: Callable[[str], None],
) -> ft.Column:
    surface = ft.Colors.BLUE_GREY_700 if dark_mode else ft.Colors.WHITE
    text_color = ft.Colors.WHITE if dark_mode else ft.Colors.BROWN_900
    muted = ft.Colors.BLUE_GREY_200 if dark_mode else ft.Colors.BROWN_500
    border_color = ft.Colors.BLUE_GREY_600 if dark_mode else ft.Colors.AMBER_100

    tasks = TASKS
    if hide_completed:
      tasks = [task for task in TASKS if task.state != "Finished"]             

    def task_row(task: ProcessingTask) -> ft.Container:
        state_color = ft.Colors.AMBER_300 if task.state == "In progress" else muted
        return ft.Container(
            bgcolor=surface,
            padding=ft.Padding.all(16),
            border=ft.Border.all(1, border_color),
            border_radius=12,
            content=ft.Row(
                controls=[
                    ft.IconButton(
                        icon=ft.Icons.PENDING_ACTIONS if task.state != "Finished" else ft.Icons.CHECK_CIRCLE,
                        icon_color=state_color,
                    ),
                    ft.Column(
                        expand=True,
                        controls=[
                            ft.Text(task.task_type, weight=ft.FontWeight.BOLD, color=text_color),
                            ft.Text(f"{task.chronicle_title} · {task.provider}", color=muted),
                        ],
                    ),
                    ft.Text(task.progress, weight=ft.FontWeight.BOLD, color=text_color),
                ],
            ),
        )

    return ft.Column(
        expand=True,
        controls=[
            ft.Text("Processing tasks", size=30, weight=ft.FontWeight.BOLD, color=text_color),
            ft.Text("Scribes keep work moving, even when you close Chronicler.", color=muted),
            ft.Divider(color=border_color),
            ft.Row(
                controls=[
                    ft.Icon(ft.Icons.SEARCH, color=muted),
                    ft.TextField(
                        expand=True,
                        value=query,
                        hint_text="Search tasks",
                        on_change=lambda event: on_query_change(event.data),
                    ),
                    ft.Divider(color=border_color),
                    ft.Checkbox(label="Hide completed tasks", value=hide_completed, on_change=lambda event: on_hide_processed_change(event.data),)                                      
                ],
            ),
            *[task_row(task) for task in tasks],
        ],
        spacing=16,
    )
