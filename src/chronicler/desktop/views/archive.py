import flet as ft

from chronicler.core.services import ChronicleService


class ArchiveView(ft.Column):
    def __init__(self, chronicle_service: ChronicleService):
        super().__init__(expand=True)
        self.chronicle_service = chronicle_service
        self.chronicle_list = ft.Column(scroll=ft.ScrollMode.ADAPTIVE, expand=True)

        self.controls = [
            ft.Row(
                [
                    ft.Text("Archive", style=ft.TextThemeStyle.HEADLINE_MEDIUM),
                    ft.IconButton(ft.Icons.REFRESH, on_click=self.refresh_clicked),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            ft.Divider(),
            self.chronicle_list,
        ]

    async def did_mount(self):
        await self.load_chronicles()

    async def refresh_clicked(self, e):
        await self.load_chronicles()

    async def load_chronicles(self):
        chronicles = await self.chronicle_service.list_chronicles()
        self.chronicle_list.controls = [
            ft.ListTile(
                title=ft.Text(c.title),
                subtitle=ft.Text(c.description or "No description"),
                leading=ft.Icon(ft.Icons.BOOK),
            )
            for c in chronicles
        ]
        if not chronicles:
            self.chronicle_list.controls = [ft.Text("No chronicles found.")]
        self.update()
