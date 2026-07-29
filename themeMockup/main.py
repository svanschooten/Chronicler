import flet as ft

from components.app_shell import AppShell


async def main(page: ft.Page):
    AppShell(page).show()


ft.run(main)
