"""Tests for the confirm-then-install flow for optional components."""

import asyncio
from unittest.mock import MagicMock, patch

import flet as ft
import pytest

from chronicler.core.config import Settings
from chronicler.core.extras import InstallResult
from chronicler.desktop.extras_prompt import ExtraInstaller
from chronicler.desktop.theme import theme_colors


@pytest.fixture
def installer(isolated_config):
    def _make(settings=None):
        return ExtraInstaller(settings or Settings(), MagicMock(), theme_colors(True))

    return _make


async def _run(installer, extra="recording"):
    """Drives `ensure` to its dialog and hands back the task, page and dialog."""
    page = MagicMock(spec=ft.Page)
    task = asyncio.ensure_future(installer.ensure(page, extra))
    await asyncio.sleep(0)
    (dialog,), _ = page.show_dialog.call_args
    return task, page, dialog


class TestAlreadyThere:
    @pytest.mark.asyncio
    async def test_an_available_extra_needs_no_dialog(self, installer):
        subject = installer()
        page = MagicMock(spec=ft.Page)

        with patch("chronicler.desktop.extras_prompt.extras.is_available", return_value=True):
            assert await subject.ensure(page, "recording") is True

        page.show_dialog.assert_not_called()


class TestConfirmation:
    @pytest.mark.asyncio
    async def test_the_dialog_names_the_component_and_its_size(self, installer):
        subject = installer()

        with patch("chronicler.desktop.extras_prompt.extras.is_available", return_value=False):
            with patch("chronicler.desktop.extras_prompt.extras.can_install", return_value=True):
                task, _, dialog = await _run(subject)
                await dialog.actions[0].on_click(MagicMock())
                await asyncio.wait_for(task, timeout=1)

        shown = " ".join(
            control.value for control in dialog.content.controls if isinstance(control, ft.Text)
        )
        assert "sounddevice" in shown
        assert "MB" in shown

    @pytest.mark.asyncio
    async def test_declining_installs_nothing(self, installer):
        subject = installer()

        with patch("chronicler.desktop.extras_prompt.extras.is_available", return_value=False):
            with patch("chronicler.desktop.extras_prompt.extras.can_install", return_value=True):
                with patch("chronicler.desktop.extras_prompt.extras.install") as install:
                    task, _, dialog = await _run(subject)
                    await dialog.actions[0].on_click(MagicMock())
                    assert await asyncio.wait_for(task, timeout=1) is False

        install.assert_not_called()

    @pytest.mark.asyncio
    async def test_accepting_installs_and_reports_success(self, installer):
        subject = installer()

        with patch("chronicler.desktop.extras_prompt.extras.is_available", return_value=False):
            with patch("chronicler.desktop.extras_prompt.extras.can_install", return_value=True):
                with patch(
                    "chronicler.desktop.extras_prompt.extras.install",
                    return_value=InstallResult(ok=True, output="ok"),
                ) as install:
                    task, _, dialog = await _run(subject)
                    await dialog.actions[1].on_click(MagicMock())
                    assert await asyncio.wait_for(task, timeout=1) is True

        install.assert_called_once_with("recording")

    @pytest.mark.asyncio
    async def test_a_failed_install_reports_the_reason(self, installer):
        subject = installer()

        with patch("chronicler.desktop.extras_prompt.extras.is_available", return_value=False):
            with patch("chronicler.desktop.extras_prompt.extras.can_install", return_value=True):
                with patch(
                    "chronicler.desktop.extras_prompt.extras.install",
                    return_value=InstallResult(ok=False, output="No matching distribution"),
                ):
                    task, _, dialog = await _run(subject)
                    await dialog.actions[1].on_click(MagicMock())
                    assert await asyncio.wait_for(task, timeout=1) is False

        reported = " ".join(str(call) for call in subject.show_snackbar.call_args_list)
        assert "No matching distribution" in reported


class TestRememberingTheChoice:
    @pytest.mark.asyncio
    async def test_the_dialog_offers_to_stop_asking(self, installer):
        subject = installer()

        with patch("chronicler.desktop.extras_prompt.extras.is_available", return_value=False):
            with patch("chronicler.desktop.extras_prompt.extras.can_install", return_value=True):
                task, _, dialog = await _run(subject)
                await dialog.actions[0].on_click(MagicMock())
                await asyncio.wait_for(task, timeout=1)

        assert any(isinstance(c, ft.Checkbox) for c in dialog.content.controls)

    @pytest.mark.asyncio
    async def test_ticking_it_saves_the_setting(self, installer, isolated_config):
        settings = Settings()
        subject = installer(settings)

        with patch("chronicler.desktop.extras_prompt.extras.is_available", return_value=False):
            with patch("chronicler.desktop.extras_prompt.extras.can_install", return_value=True):
                with patch(
                    "chronicler.desktop.extras_prompt.extras.install",
                    return_value=InstallResult(ok=True, output=""),
                ):
                    task, _, dialog = await _run(subject)
                    checkbox = next(
                        c for c in dialog.content.controls if isinstance(c, ft.Checkbox)
                    )
                    checkbox.value = True
                    await dialog.actions[1].on_click(MagicMock())
                    await asyncio.wait_for(task, timeout=1)

        assert settings.extras.auto_install is True
        assert "auto_install: true" in settings.save_path().read_text()

    @pytest.mark.asyncio
    async def test_leaving_it_alone_keeps_asking(self, installer, isolated_config):
        settings = Settings()
        subject = installer(settings)

        with patch("chronicler.desktop.extras_prompt.extras.is_available", return_value=False):
            with patch("chronicler.desktop.extras_prompt.extras.can_install", return_value=True):
                with patch(
                    "chronicler.desktop.extras_prompt.extras.install",
                    return_value=InstallResult(ok=True, output=""),
                ):
                    task, _, dialog = await _run(subject)
                    await dialog.actions[1].on_click(MagicMock())
                    await asyncio.wait_for(task, timeout=1)

        assert settings.extras.auto_install is False


class TestAutoInstall:
    @pytest.mark.asyncio
    async def test_the_setting_skips_the_dialog(self, installer, isolated_config):
        settings = Settings()
        settings.extras.auto_install = True
        subject = installer(settings)
        page = MagicMock(spec=ft.Page)

        with patch("chronicler.desktop.extras_prompt.extras.is_available", return_value=False):
            with patch("chronicler.desktop.extras_prompt.extras.can_install", return_value=True):
                with patch(
                    "chronicler.desktop.extras_prompt.extras.install",
                    return_value=InstallResult(ok=True, output=""),
                ) as install:
                    assert await subject.ensure(page, "recording") is True

        page.show_dialog.assert_not_called()
        install.assert_called_once_with("recording")

    @pytest.mark.asyncio
    async def test_it_still_says_what_it_is_doing(self, installer, isolated_config):
        settings = Settings()
        settings.extras.auto_install = True
        subject = installer(settings)

        with patch("chronicler.desktop.extras_prompt.extras.is_available", return_value=False):
            with patch("chronicler.desktop.extras_prompt.extras.can_install", return_value=True):
                with patch(
                    "chronicler.desktop.extras_prompt.extras.install",
                    return_value=InstallResult(ok=True, output=""),
                ):
                    await subject.ensure(MagicMock(spec=ft.Page), "recording")

        assert subject.show_snackbar.call_count >= 1


class TestUninstallableEnvironment:
    @pytest.mark.asyncio
    async def test_it_explains_instead_of_offering(self, installer):
        subject = installer()
        page = MagicMock(spec=ft.Page)

        with patch("chronicler.desktop.extras_prompt.extras.is_available", return_value=False):
            with patch("chronicler.desktop.extras_prompt.extras.can_install", return_value=False):
                assert await subject.ensure(page, "recording") is False

        page.show_dialog.assert_not_called()
        reported = " ".join(str(call) for call in subject.show_snackbar.call_args_list)
        assert "chronicler[recording]" in reported
