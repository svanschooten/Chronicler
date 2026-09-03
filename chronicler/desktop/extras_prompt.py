"""Confirming, then installing, an optional component the user has just asked to use."""

import asyncio
import logging
from collections.abc import Callable

import flet as ft

from chronicler.core import extras
from chronicler.core.config import Settings
from chronicler.desktop.dialogs import await_dialog
from chronicler.desktop.theme import ThemeColors
from chronicler.i18n import t

logger = logging.getLogger(__name__)


class ExtraInstaller:
    """
    Makes sure an optional dependency is there before the feature that needs it runs.

    A download is always confirmed unless the user has waived it, in which case they still
    get told it is happening. Package names and pip commands come from the registry rather
    than the message catalogue - they are the same in every language. See
    docs/optional-extras.md.
    """

    def __init__(
        self,
        settings: Settings,
        show_snackbar: Callable[[str], None],
        colors: ThemeColors,
    ):
        self.settings = settings
        self.show_snackbar = show_snackbar
        self.colors = colors

    async def ensure(self, page: ft.Page, name: str) -> bool:
        """True when `name` is usable by the time this returns."""
        if extras.is_available(name):
            return True

        if not extras.can_install():
            self.show_snackbar(extras.missing_message(name))
            return False

        if self.settings.extras.auto_install:
            return await self._install(name)

        if not await self._ask(page, name):
            logger.info(f"The user declined to install the {name} extra")
            return False
        return await self._install(name)

    async def _ask(self, page: ft.Page, name: str) -> bool:
        extra = extras.get_extra(name)
        remember = ft.Checkbox(label=t("extras.remember"), value=False)

        body: list[ft.Control] = [
            ft.Text(
                t(
                    "extras.message",
                    purpose=extra.purpose,
                    requirement=extra.requirement,
                    size=extras.download_estimate(name),
                ),
                color=self.colors.text,
            )
        ]
        if extra.note:
            body.append(ft.Text(extra.note, size=12, color=self.colors.muted))
        if extra.system_packages:
            body.append(ft.Text(extra.apt_hint, size=12, font_family="monospace"))
        body.append(remember)

        def build(on_choice) -> ft.AlertDialog:
            return ft.AlertDialog(
                title=ft.Text(t("extras.title")),
                content=ft.Column(body, tight=True, width=440),
                actions=[
                    ft.TextButton(t("extras.not_now"), on_click=on_choice(lambda: False)),
                    ft.FilledButton(t("extras.install"), on_click=on_choice(lambda: True)),
                ],
            )

        accepted = bool(await await_dialog(page, build))
        if accepted and remember.value:
            self._remember()
        return accepted

    def _remember(self) -> None:
        self.settings.extras.auto_install = True
        try:
            self.settings.save()
        except OSError as error:
            logger.warning(f"Could not save the auto-install preference: {error}")

    async def _install(self, name: str) -> bool:
        extra = extras.get_extra(name)
        self.show_snackbar(
            t("extras.installing", name=extra.requirement, size=extras.download_estimate(name))
        )

        result = await asyncio.to_thread(extras.install, name)
        if result.ok:
            self.show_snackbar(t("extras.installed", name=extra.requirement))
        else:
            self.show_snackbar(t("extras.failed", name=extra.name, error=result.output))
        return result.ok
