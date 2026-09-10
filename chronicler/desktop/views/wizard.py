"""
The first-run setup screen for the desktop app.

The console wizard in `core.wizard` cannot serve a packaged desktop build: with no console
attached there is nowhere for `input()` to read from, and a windowless Windows executable
has no stdio at all. This asks the same questions through Flet instead.

It covers only the two modes a desktop window can actually run in - full stack and thin
client. Server and web-client setup stays in the console wizard, which runs from the
terminal those modes are started from anyway.
"""

import asyncio
import logging
import secrets
from pathlib import Path

import flet as ft

from chronicler.core.config import Settings
from chronicler.core.wizard import LANGUAGE_NAMES, default_workspace_path, supported_languages
from chronicler.desktop.picking import FilePickerFlow
from chronicler.desktop.theme import theme_colors
from chronicler.i18n import set_locale, t

logger = logging.getLogger(__name__)

FULL_STACK = "desktop:full_stack"
THIN_CLIENT = "desktop:thin_client"

CARD_WIDTH = 560


class FletSetupWizard:
    """
    Collects the same settings the console wizard does, one step at a time, and saves them.

    `run()` returns only once the user has finished, so the caller can treat it as "config
    now exists" and carry on building the runtime.
    """

    def __init__(self, page: ft.Page, settings: Settings):
        self.page = page
        self.settings = settings
        self.colors = theme_colors(settings.dark_mode)
        self.file_picker: ft.FilePicker | None = None
        self.picker = FilePickerFlow(lambda: self.file_picker, self.show_snackbar)

        self.language = settings.ui.locale or supported_languages()[0]
        self.mode = FULL_STACK
        self.workspace_path: Path | None = settings.workspace_path
        self.server_url = settings.server_url or ""
        self.api_key: str | None = settings.api_key

        self._root = ft.Container(expand=True, bgcolor=self.colors.surface, padding=32)
        self._done: asyncio.Future[None] | None = None

    # -- lifecycle ------------------------------------------------------------

    async def run(self) -> None:
        """Shows the wizard and returns once the user has completed it."""
        done: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._done = done

        self.apply_theme()
        self._ensure_picker()
        self.show_language()
        self.page.add(self._root)

        await done

    def apply_theme(self) -> None:
        """
        Material's own widgets - the dropdown, the text fields, the buttons - follow
        `page.theme_mode` rather than the colours painted here. Left at its default the page
        follows the OS, so a dark workspace on a light desktop drew dark-on-dark inside the
        card. DesktopApp does the same thing once it takes over.
        """
        dark = self.settings.dark_mode
        self.page.theme_mode = ft.ThemeMode.DARK if dark else ft.ThemeMode.LIGHT
        self.page.bgcolor = self.colors.surface

    def _ensure_picker(self) -> None:
        """The workspace step needs a native folder dialog; it lives in `page.services`."""
        if self.file_picker is None:
            self.file_picker = ft.FilePicker()
        if self.file_picker not in self.page.services:
            self.page.services.append(self.file_picker)

    def _release_picker(self) -> None:
        """The views that come next register pickers of their own; this one is done."""
        if self.file_picker is not None and self.file_picker in self.page.services:
            self.page.services.remove(self.file_picker)

    def show_snackbar(self, message: str) -> None:
        self.page.show_dialog(ft.SnackBar(ft.Text(message)))

    def _finish(self) -> None:
        """Writes everything collected to the config file and releases `run()`."""
        self.settings.ui.locale = self.language
        self.settings.transcription.language = self.language
        self.settings.mode = self.mode
        if self.mode == FULL_STACK:
            self.settings.workspace_path = self.workspace_path
            self.settings.server_url = None
        else:
            self.settings.server_url = self.server_url
            self.settings.workspace_path = None
        self.settings.api_key = self.api_key

        config_file = self.settings.save()
        logger.info(f"Setup wizard saved the configuration to {config_file}")

        self._release_picker()
        self.show_saving(config_file)
        if self._done is not None and not self._done.done():
            self._done.set_result(None)

    # -- frame ----------------------------------------------------------------

    def _render(
        self,
        step: int,
        title: str,
        description: str,
        body: list[ft.Control],
        actions: list[ft.Control],
    ) -> None:
        """
        Repaints the whole screen, header included.

        Everything is rebuilt from `t()` on every step rather than updated in place, so the
        language step relabels the wizard around it the moment it is answered.
        """
        self._root.content = ft.Column(
            [
                ft.Text(
                    t("wizard.title"),
                    size=30,
                    weight=ft.FontWeight.BOLD,
                    color=self.colors.text,
                ),
                ft.Text(t("wizard.subtitle"), color=self.colors.muted),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                t("wizard.step", number=step, total=self._total_steps()),
                                size=12,
                                color=self.colors.muted,
                            ),
                            ft.Text(
                                title, size=20, weight=ft.FontWeight.BOLD, color=self.colors.text
                            ),
                            ft.Text(description, color=self.colors.muted),
                            ft.Divider(height=16, color=self.colors.border),
                            *body,
                        ],
                        spacing=12,
                        tight=True,
                    ),
                    bgcolor=self.colors.card,
                    border=ft.Border.all(1, self.colors.border),
                    border_radius=12,
                    padding=24,
                    width=CARD_WIDTH,
                ),
                ft.Row(
                    actions,
                    alignment=ft.MainAxisAlignment.END,
                    width=CARD_WIDTH,
                    spacing=8,
                ),
            ],
            spacing=16,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self.page.update()

    def _total_steps(self) -> int:
        """Thin client asks for a server instead of a workspace *and* a key, so it is shorter."""
        return 4 if self.mode == FULL_STACK else 3

    def _back(self, target) -> ft.Control:
        return ft.TextButton(t("wizard.back"), on_click=lambda _event: target())

    # -- step 1: language -----------------------------------------------------

    def show_language(self) -> None:
        field = ft.Dropdown(
            label=t("wizard.language.label"),
            value=self.language,
            options=[
                ft.DropdownOption(key=code, text=LANGUAGE_NAMES[code])
                for code in supported_languages()
            ],
            width=280,
        )

        def confirm(_event) -> None:
            self.language = field.value or self.language
            set_locale(self.language)
            self.show_mode()

        self._render(
            1,
            t("wizard.language.title"),
            t("wizard.language.description"),
            [field],
            [ft.FilledButton(t("wizard.next"), on_click=confirm)],
        )

    # -- step 2: mode ---------------------------------------------------------

    def show_mode(self) -> None:
        def choose(mode: str):
            def handler(_event) -> None:
                self.mode = mode
                self.show_workspace() if mode == FULL_STACK else self.show_server()

            return handler

        self._render(
            2,
            t("wizard.mode.title"),
            t("wizard.mode.description"),
            [
                self._choice_card(
                    ft.Icons.COMPUTER,
                    t("wizard.mode.full_stack"),
                    t("wizard.mode.full_stack_description"),
                    choose(FULL_STACK),
                ),
                self._choice_card(
                    ft.Icons.CLOUD_OUTLINED,
                    t("wizard.mode.thin_client"),
                    t("wizard.mode.thin_client_description"),
                    choose(THIN_CLIENT),
                ),
                ft.Text(t("wizard.mode.server_note"), size=12, color=self.colors.muted),
            ],
            [self._back(self.show_language)],
        )

    def _choice_card(self, icon: ft.IconData, title: str, description: str, on_click) -> ft.Control:
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(icon, color=self.colors.accent),
                    ft.Column(
                        [
                            ft.Text(title, weight=ft.FontWeight.BOLD, color=self.colors.text),
                            ft.Text(description, size=12, color=self.colors.muted),
                        ],
                        spacing=2,
                        tight=True,
                        expand=True,
                    ),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, color=self.colors.muted),
                ],
                spacing=12,
            ),
            border=ft.Border.all(1, self.colors.border),
            border_radius=8,
            padding=16,
            on_click=on_click,
            ink=True,
        )

    # -- step 3a: workspace ---------------------------------------------------

    def show_workspace(self) -> None:
        field = ft.TextField(
            label=t("wizard.workspace.label"),
            value=str(self.workspace_path or default_workspace_path()),
            expand=True,
        )

        async def browse(_event) -> None:
            chosen = await self.picker.pick_directory(t("wizard.workspace.picker_title"))
            if chosen:
                field.value = chosen
                field.error = None
                self.page.update()

        def confirm(_event) -> None:
            chosen = (field.value or "").strip()
            if not chosen:
                field.error = t("wizard.workspace.required")
                self.page.update()
                return
            self.workspace_path = Path(chosen).expanduser().resolve()
            self.show_api_key()

        self._render(
            3,
            t("wizard.workspace.title"),
            t("wizard.workspace.description"),
            [
                ft.Row(
                    [
                        field,
                        ft.OutlinedButton(
                            t("wizard.workspace.browse"),
                            icon=ft.Icons.FOLDER_OPEN,
                            on_click=browse,
                        ),
                    ],
                    spacing=8,
                )
            ],
            [
                self._back(self.show_mode),
                ft.FilledButton(t("wizard.next"), on_click=confirm),
            ],
        )

    # -- step 4a: api key -----------------------------------------------------

    def show_api_key(self) -> None:
        field = ft.TextField(
            label=t("wizard.api_key.label"),
            value=self.api_key or secrets.token_urlsafe(32),
            password=True,
            can_reveal_password=True,
            expand=True,
        )

        def regenerate(_event) -> None:
            field.value = secrets.token_urlsafe(32)
            self.page.update()

        def skip(_event) -> None:
            self.api_key = None
            self._finish()

        def confirm(_event) -> None:
            self.api_key = (field.value or "").strip() or None
            self._finish()

        self._render(
            4,
            t("wizard.api_key.title"),
            t("wizard.api_key.description"),
            [
                ft.Row([field], spacing=8),
                ft.OutlinedButton(
                    t("wizard.api_key.generate"),
                    icon=ft.Icons.REFRESH,
                    on_click=regenerate,
                ),
            ],
            [
                self._back(self.show_workspace),
                ft.TextButton(t("wizard.api_key.skip"), on_click=skip),
                ft.FilledButton(t("wizard.finish"), on_click=confirm),
            ],
        )

    # -- step 3b: remote server -----------------------------------------------

    def show_server(self) -> None:
        """
        The thin-client branch, where both fields are required.

        Unlike the full-stack step the key cannot be generated here: it has to match one the
        server operator already set, and a made-up key would 403 every request instead.

        Flet 0.86 spells validation differently per control - a TextField carries `error`, a
        Dropdown carries `error_text`. See docs/desktop.md.
        """
        url_field = ft.TextField(
            label=t("wizard.server.url_label"),
            hint_text=t("wizard.server.url_hint"),
            value=self.server_url,
        )
        key_field = ft.TextField(
            label=t("wizard.server.key_label"),
            value=self.api_key or "",
            password=True,
            can_reveal_password=True,
        )

        def confirm(_event) -> None:
            url = (url_field.value or "").strip()
            key = (key_field.value or "").strip()
            url_field.error = None if url else t("wizard.server.url_required")
            key_field.error = None if key else t("wizard.server.key_required")
            if not url or not key:
                self.page.update()
                return

            self.server_url = url
            self.api_key = key
            self._finish()

        self._render(
            3,
            t("wizard.server.title"),
            t("wizard.server.description"),
            [
                url_field,
                key_field,
                ft.Text(t("wizard.server.key_description"), size=12, color=self.colors.muted),
            ],
            [
                self._back(self.show_mode),
                ft.FilledButton(t("wizard.finish"), on_click=confirm),
            ],
        )

    # -- done -----------------------------------------------------------------

    def show_saving(self, config_file: Path) -> None:
        """
        Stays on screen while the caller opens the databases or reaches the server, so the
        window is never blank between the last click and the app appearing.
        """
        self._render(
            self._total_steps(),
            t("wizard.saving.title"),
            t("wizard.saving.saved", path=config_file),
            [ft.ProgressRing(width=24, height=24)],
            [],
        )
