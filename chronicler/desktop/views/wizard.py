import secrets
from pathlib import Path

import flet as ft

from chronicler.core.config import Settings

LANGUAGE_NAMES = {"en": "English", "nl": "Nederlands", "de": "Deutsch"}


def supported_languages() -> list[str]:
    return list(LANGUAGE_NAMES)


def default_workspace_path() -> Path:
    home = Path.home()
    documents = home / "Documents"
    base = documents if documents.is_dir() else home
    return (base / "Chronicler").expanduser()


class SetupWizard:
    def __init__(
        self,
        page: ft.Page,
        settings: Settings,
        on_complete: callable,
        dark_mode: bool = False,
    ):
        self.page = page
        self.settings = settings
        self.on_complete = on_complete
        self.dark_mode = dark_mode

        self._mode: str | None = None
        self._language: str = "en"
        self._workspace_path: Path | None = None
        self._api_key: str | None = None
        self._server_url: str | None = None

        self.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Chronicler Setup"),
            content=ft.Container(width=500, height=400),
            actions=[],
            actions_alignment=ft.MainAxisAlignment.END,
            inset_padding=40,
        )
        self._show_mode_selection()

    def open(self):
        self.page.dialog = self.dialog
        self.dialog.open = True
        self.page.update()

    def _close(self):
        self.dialog.open = False
        self.page.update()
        self.on_complete()

    def _update_content(self, content: ft.Control, actions: list[ft.Control] | None = None):
        self.dialog.content.content = content
        self.dialog.actions = actions or []
        self.page.update()

    def _show_mode_selection(self):
        def select_mode(mode: str, label: str):
            mode_map = {
                "Full Stack": "desktop:full_stack",
                "Thin Client": "desktop:thin_client",
                "Server": "server",
                "Web Client": "client:web",
            }
            self._mode = mode_map.get(mode)
            self._show_language_step()

        content = ft.Column(
            [
                ft.Text("How would you like to run Chronicler?", size=16),
                ft.Divider(height=10),
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.COMPUTER),
                    title=ft.Text("Full Stack"),
                    subtitle=ft.Text("Local processing and storage"),
                    on_click=lambda e: select_mode("Full Stack", e),
                ),
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.TABLET),
                    title=ft.Text("Thin Client"),
                    subtitle=ft.Text("Connect to remote server"),
                    on_click=lambda e: select_mode("Thin Client", e),
                ),
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.CLOUD),
                    title=ft.Text("Server"),
                    subtitle=ft.Text("Run as server for other clients"),
                    on_click=lambda e: select_mode("Server", e),
                ),
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.WEB),
                    title=ft.Text("Web Client"),
                    subtitle=ft.Text("Browser-based interface"),
                    on_click=lambda e: select_mode("Web Client", e),
                ),
            ],
            scroll=ft.ScrollMode.AUTO,
        )

        self._update_content(content, [])

    def _show_language_step(self):
        language_dropdown = ft.Dropdown(
            label="Language",
            value="en",
            options=[
                ft.dropdown.Option(key=code, text=f"{LANGUAGE_NAMES[code]} ({code})")
                for code in supported_languages()
            ],
            width=300,
        )

        def continue_click(e):
            self._language = language_dropdown.value
            if self._mode in ("desktop:full_stack", "server"):
                self._show_workspace_step()
            else:
                self._show_server_step()

        content = ft.Column(
            [
                ft.Text("Select your language", size=16),
                ft.Divider(height=10),
                language_dropdown,
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

        actions = [
            ft.TextButton("Back", on_click=lambda e: self._show_mode_selection()),
            ft.ElevatedButton("Continue", on_click=continue_click),
        ]

        self._update_content(content, actions)

    def _show_workspace_step(self):
        path_field = ft.TextField(
            label="Workspace Path",
            value=str(default_workspace_path()),
            width=400,
            suffix=ft.IconButton(
                icon=ft.Icons.FOLDER_OPEN,
                on_click=lambda e: self._pick_folder(path_field),
            ),
        )

        def continue_click(e):
            path = path_field.value.strip()
            self._workspace_path = Path(path).expanduser().resolve() if path else default_workspace_path()
            self._show_api_key_step()

        content = ft.Column(
            [
                ft.Text("Choose workspace location", size=16),
                ft.Text("Chronicler stores recordings and databases here.", size=12, color=ft.colors.GREY_600),
                ft.Divider(height=10),
                path_field,
            ],
            alignment=ft.MainAxisAlignment.CENTER,
        )

        actions = [
            ft.TextButton("Back", on_click=lambda e: self._show_language_step()),
            ft.ElevatedButton("Continue", on_click=continue_click),
        ]

        self._update_content(content, actions)

    def _pick_folder(self, text_field: ft.TextField):
        def on_result(e: ft.FilePickerResultEvent):
            if e.path:
                text_field.value = e.path
                text_field.update()

        picker = ft.FilePicker(on_result=on_result)
        self.page.overlay.append(picker)
        self.page.update()
        picker.get_directory_path()

    def _show_api_key_step(self):
        key_field = ft.TextField(
            label="API Key (leave blank to generate)",
            password=True,
            can_reveal_password=True,
            width=400,
        )

        def generate_click(e):
            key_field.value = secrets.token_urlsafe(32)
            key_field.update()

        def continue_click(e):
            key = key_field.value.strip()
            self._api_key = key if key else secrets.token_urlsafe(32)
            self._finish()

        def skip_click(e):
            self._api_key = None
            self._finish(skip_api_key=True)

        content = ft.Column(
            [
                ft.Text("API Key Setup", size=16),
                ft.Text("Required for remote access to this instance.", size=12, color=ft.colors.GREY_600),
                ft.Divider(height=10),
                key_field,
                ft.ElevatedButton("Generate", on_click=generate_click, width=150),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
        )

        actions = [
            ft.TextButton("Back", on_click=lambda e: self._show_workspace_step()),
            ft.TextButton("Skip", on_click=skip_click),
            ft.ElevatedButton("Continue", on_click=continue_click),
        ]

        self._update_content(content, actions)

    def _show_server_step(self):
        url_field = ft.TextField(
            label="Server URL",
            hint_text="http://localhost:8000",
            width=400,
        )
        key_field = ft.TextField(
            label="API Key",
            password=True,
            can_reveal_password=True,
            width=400,
        )

        def continue_click(e):
            has_error = False
            if not url_field.value.strip():
                url_field.error_text = "Required"
                has_error = True
            else:
                url_field.error_text = None

            if not key_field.value.strip():
                key_field.error_text = "Required"
                has_error = True
            else:
                key_field.error_text = None

            if has_error:
                url_field.update()
                key_field.update()
                return

            self._server_url = url_field.value.strip()
            self._api_key = key_field.value.strip()
            self._finish()

        content = ft.Column(
            [
                ft.Text("Connect to Server", size=16),
                ft.Divider(height=10),
                url_field,
                ft.Divider(height=10, color="transparent"),
                key_field,
            ],
            alignment=ft.MainAxisAlignment.CENTER,
        )

        actions = [
            ft.TextButton("Back", on_click=lambda e: self._show_language_step()),
            ft.ElevatedButton("Continue", on_click=continue_click),
        ]

        self._update_content(content, actions)

    def _finish(self, skip_api_key: bool = False):
        self.settings.ui.locale = self._language
        self.settings.transcription.language = self._language
        self.settings.mode = self._mode

        if self._workspace_path:
            self.settings.workspace_path = self._workspace_path
        if self._server_url:
            self.settings.server_url = self._server_url

        # Only set api_key if not skipped
        if skip_api_key:
            self.settings.api_key = None
        elif self._api_key:
            self.settings.api_key = self._api_key

        self.settings.save()
        self._close()