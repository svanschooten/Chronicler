import logging
from collections.abc import Awaitable, Callable

import flet as ft

from chronicler.core.config import Settings
from chronicler.core.config_sections import WHISPER_MODEL_SIZES, language_choices
from chronicler.desktop.theme import theme_colors
from chronicler.desktop.views.settings.editor import SettingsEditor
from chronicler.desktop.widgets import amber_button
from chronicler.i18n import available_locales, set_locale, t

logger = logging.getLogger(__name__)


class SettingsView(ft.Column):
    def __init__(
        self,
        settings: Settings,
        on_dark_mode_change: Callable[[bool], Awaitable[None]] | None = None,
        on_locale_change: Callable[[str], Awaitable[None]] | None = None,
    ):
        self.settings = settings
        self.editor = SettingsEditor(settings)
        self.on_dark_mode_change = on_dark_mode_change
        self.on_locale_change = on_locale_change
        self.colors = theme_colors(settings.dark_mode)
        self.file_picker: ft.FilePicker | None = None

        super().__init__(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=16,
            controls=[
                ft.Text(t("settings.title"), size=30, weight=ft.FontWeight.BOLD),
                ft.Text(t("settings.subtitle"), color=self.colors.muted),
                *self._appearance(),
                *self._workspace(),
                *self._connection(),
                *self._transcription(),
                *self._cleaning(),
                *self._llm(),
            ],
        )

    # -- sections -------------------------------------------------------------

    def _heading(self, key: str) -> ft.Text:
        return ft.Text(t(key), size=18, weight=ft.FontWeight.BOLD)

    def _appearance(self) -> list[ft.Control]:
        return [
            self._heading("settings.appearance.title"),
            self.setting_card(
                t("settings.appearance.dark_mode"),
                t("settings.appearance.dark_mode_description"),
                ft.Switch(value=self.settings.dark_mode, on_change=self._dark_mode_changed),
            ),
            self.setting_card(
                t("settings.appearance.language"),
                t("settings.appearance.language_description"),
                self._dropdown(
                    "ui.locale",
                    available_locales(),
                    self.settings.ui.locale,
                    on_change=self._locale_changed,
                ),
            ),
        ]

    def _workspace(self) -> list[ft.Control]:
        if self.settings.workspace_path:
            description = str(self.settings.workspace_path)
        elif self.settings.server_url:
            description = t("settings.workspace.not_configured_thin")
        else:
            description = t("settings.workspace.not_configured")

        self.workspace_text = ft.Text(description, color=self.colors.muted)
        return [
            self._heading("settings.workspace.title"),
            self.setting_card(
                t("settings.workspace.local"),
                description,
                ft.IconButton(
                    icon=ft.Icons.FOLDER_OPEN,
                    icon_color=self.colors.muted,
                    tooltip=t("settings.workspace.choose"),
                    on_click=self.pick_workspace_clicked,
                ),
                description_control=self.workspace_text,
            ),
        ]

    def _connection(self) -> list[ft.Control]:
        if self.settings.server_url:
            title = t("settings.connection.remote_server")
            description = self.settings.server_url
            badge = t("settings.connection.thin_client")
        else:
            title = t("settings.connection.service_layer")
            description = t("settings.connection.local_ready")
            badge = t("settings.connection.full_stack")

        return [
            self._heading("settings.connection.title"),
            self.setting_card(
                title,
                description,
                ft.Text(badge, weight=ft.FontWeight.BOLD, color=self.colors.accent),
            ),
        ]

    def _transcription(self) -> list[ft.Control]:
        return [
            self._heading("settings.transcription.title"),
            self.setting_card(
                t("settings.transcription.language"),
                t("settings.transcription.language_description"),
                self._dropdown(
                    "transcription.language",
                    language_choices(self.settings.transcription, available_locales()),
                    self.editor.get_language(),
                ),
            ),
            self.setting_card(
                t("settings.transcription.model_size"),
                t("settings.transcription.model_size_description"),
                self._dropdown(
                    "transcription.model_size",
                    WHISPER_MODEL_SIZES,
                    self.settings.transcription.model_size,
                ),
            ),
            self.setting_card(
                t("settings.transcription.no_speech_threshold"),
                t("settings.transcription.no_speech_threshold_description"),
                self._text_field("transcription.no_speech_threshold", width=90),
            ),
            self.setting_card(
                t("settings.transcription.normalize_first"),
                t("settings.transcription.normalize_first_description"),
                ft.Switch(
                    value=self.settings.transcription.normalize_first,
                    data="transcription.normalize_first",
                    on_change=self._switch_changed,
                ),
            ),
        ]

    def _cleaning(self) -> list[ft.Control]:
        return [
            self._heading("settings.cleaning.title"),
            self.setting_card(
                t("settings.cleaning.hallucination_phrases"),
                t("settings.cleaning.hallucination_phrases_description"),
                self._text_field(
                    "cleaning.hallucination_phrases", width=260, multiline=True, max_lines=6
                ),
            ),
            self.setting_card(
                t("settings.cleaning.hallucination_match"),
                t("settings.cleaning.hallucination_match_description"),
                self._dropdown(
                    "cleaning.hallucination_match",
                    ["normalized", "exact", "regex"],
                    self.settings.cleaning.hallucination_match,
                ),
            ),
            self.setting_card(
                t("settings.cleaning.repetition_window"),
                t("settings.cleaning.repetition_window_description"),
                self._text_field("cleaning.repetition_window_seconds", width=90),
            ),
            self.setting_card(
                t("settings.cleaning.strip_patterns"),
                t("settings.cleaning.strip_patterns_description"),
                self._text_field("cleaning.strip_patterns", width=260, multiline=True, max_lines=4),
            ),
            ft.Row(
                controls=[
                    ft.TextButton(
                        t("settings.restore_defaults"),
                        data="cleaning",
                        on_click=self.restore_defaults_clicked,
                    )
                ],
                alignment=ft.MainAxisAlignment.END,
            ),
        ]

    def _llm(self) -> list[ft.Control]:
        return [
            self._heading("settings.llm.title"),
            self.setting_card(
                t("settings.llm.provider"),
                t("settings.llm.provider_description"),
                self._dropdown(
                    "llm.provider",
                    ["none", "openai_compatible", "llama_cpp"],
                    self.settings.llm.provider,
                    labels={
                        "none": t("settings.llm.provider_none"),
                        "openai_compatible": t("settings.llm.provider_openai_compatible"),
                        "llama_cpp": t("settings.llm.provider_llama_cpp"),
                    },
                ),
            ),
            self.setting_card(
                t("settings.llm.base_url"),
                t("settings.llm.base_url_description"),
                self._text_field("llm.base_url", width=260),
            ),
            self.setting_card(
                t("settings.llm.api_key"),
                "",
                self._text_field("llm.api_key", width=260, secret=True),
            ),
            self.setting_card(
                t("settings.llm.model"), "", self._text_field("llm.model", width=260)
            ),
            self.setting_card(
                t("settings.llm.model_path"), "", self._text_field("llm.model_path", width=260)
            ),
        ]

    # -- controls -------------------------------------------------------------

    def _dropdown(
        self,
        path: str,
        options: list[str],
        value: str,
        labels: dict[str, str] | None = None,
        on_change=None,
    ) -> ft.Dropdown:
        return ft.Dropdown(
            width=200,
            value=value,
            data=path,
            options=[
                ft.DropdownOption(key=option, text=(labels or {}).get(option, option))
                for option in options
            ],
            on_select=on_change or self._value_changed,
        )

    def _text_field(
        self,
        path: str,
        width: int = 200,
        multiline: bool = False,
        max_lines: int | None = None,
        secret: bool = False,
    ) -> ft.TextField:
        return ft.TextField(
            width=width,
            value=self.editor.as_text(path),
            data=path,
            multiline=multiline,
            max_lines=max_lines,
            password=secret,
            can_reveal_password=secret,
            on_blur=self._value_changed,
            on_submit=self._value_changed,
        )

    def setting_card(
        self,
        title: str,
        description: str,
        content: ft.Control,
        description_control: ft.Control | None = None,
    ) -> ft.Container:
        return ft.Container(
            bgcolor=self.colors.card,
            padding=ft.Padding.all(18),
            border=ft.Border.all(1, self.colors.border),
            border_radius=12,
            content=ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Column(
                        expand=True,
                        spacing=2,
                        controls=[
                            ft.Text(title, weight=ft.FontWeight.BOLD, color=self.colors.text),
                            description_control or ft.Text(description, color=self.colors.muted),
                        ],
                    ),
                    content,
                ],
            ),
        )

    # -- handlers -------------------------------------------------------------

    async def _value_changed(self, e):
        await self.apply(e.control.data, e.control.value)

    async def _switch_changed(self, e):
        await self.apply(e.control.data, e.control.value)

    async def apply(self, path: str, value) -> bool:
        """Validates and persists one setting, reporting the outcome to the user."""
        try:
            self.editor.set(path, value)
            self.editor.save()
        except (ValueError, KeyError, OSError) as error:
            logger.warning(f"Rejected settings change {path}={value!r}: {error}")
            self.show_snackbar(t("settings.save_failed", error=error))
            return False
        self.show_snackbar(t("settings.saved"))
        return True

    async def _dark_mode_changed(self, e):
        await self.apply("dark_mode", e.control.value)
        if self.on_dark_mode_change is not None:
            await self.on_dark_mode_change(e.control.value)

    async def _locale_changed(self, e):
        if not await self.apply("ui.locale", e.control.value):
            return
        set_locale(e.control.value)
        if self.on_locale_change is not None:
            await self.on_locale_change(e.control.value)

    async def restore_defaults_clicked(self, e):
        self.editor.restore_defaults(e.control.data)
        self.editor.save()
        self.show_snackbar(t("settings.saved"))

    async def pick_workspace_clicked(self, e):
        if self.file_picker is None:
            self.show_snackbar(t("export.no_picker"))
            return
        chosen = await self.file_picker.get_directory_path(
            dialog_title=t("settings.workspace.choose")
        )
        if not chosen:
            return
        if await self.apply("workspace_path", chosen):
            self.workspace_text.value = t("settings.workspace.changed", path=chosen)
            self._refresh(self.workspace_text)

    @staticmethod
    def _refresh(control: ft.Control) -> None:
        """Repaints a control, tolerating one that is not attached to a page yet."""
        try:
            control.update()
        except (RuntimeError, AssertionError):
            pass

    def show_snackbar(self, message: str):
        if self.page is not None:
            self.page.show_dialog(ft.SnackBar(ft.Text(message)))

    # -- lifecycle ------------------------------------------------------------

    def did_mount(self):
        if self.file_picker is None:
            self.file_picker = ft.FilePicker()
        if self.file_picker not in self.page.services:
            self.page.services.append(self.file_picker)
            self.page.update()

    def will_unmount(self):
        if self.file_picker and self.file_picker in self.page.services:
            self.page.services.remove(self.file_picker)
            self.page.update()


__all__ = ["SettingsView", "amber_button"]
