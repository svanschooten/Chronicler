"""Tests for the record-a-source dialog."""

from unittest.mock import AsyncMock, MagicMock, patch

import flet as ft
import pytest

from chronicler.core.models import Chronicle
from chronicler.core.recording import InputDevice, RecordingError
from chronicler.desktop.theme import theme_colors
from chronicler.desktop.views.transcript.recording import RecordingDialog


@pytest.fixture
def make_dialog():
    def _make(installer=None):
        dialog = RecordingDialog(
            Chronicle(title="Session One"),
            AsyncMock(),
            AsyncMock(),
            MagicMock(),
            theme_colors(True),
            installer=installer,
        )
        return dialog

    return _make


class TestMissingComponent:
    @pytest.mark.asyncio
    async def test_it_offers_to_install_before_looking_for_devices(self, make_dialog):
        installer = MagicMock()
        installer.ensure = AsyncMock(return_value=False)
        dialog = make_dialog(installer)
        page = MagicMock(spec=ft.Page)

        with patch(
            "chronicler.desktop.views.transcript.recording.list_input_devices"
        ) as list_devices:
            await dialog.run(page)

        installer.ensure.assert_awaited_once_with(page, "recording")
        list_devices.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_successful_install_carries_on_to_the_devices(self, make_dialog):
        installer = MagicMock()
        installer.ensure = AsyncMock(return_value=True)
        dialog = make_dialog(installer)

        with patch(
            "chronicler.desktop.views.transcript.recording.list_input_devices",
            return_value=[InputDevice(index=0, name="Mic", channels=1)],
        ) as list_devices:
            with patch(
                "chronicler.desktop.views.transcript.recording.await_dialog",
                new=AsyncMock(return_value=None),
            ):
                await dialog.run(MagicMock(spec=ft.Page))

        list_devices.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_no_installer_it_still_reports_the_backend_failure(self, make_dialog):
        dialog = make_dialog()

        with patch(
            "chronicler.desktop.views.transcript.recording.list_input_devices",
            side_effect=RecordingError("no PortAudio"),
        ):
            await dialog.run(MagicMock(spec=ft.Page))

        dialog.show_snackbar.assert_called_once()
        assert "no PortAudio" in dialog.show_snackbar.call_args[0][0]


class TestNoDevices:
    @pytest.mark.asyncio
    async def test_an_empty_device_list_says_so_rather_than_opening_an_empty_picker(
        self, make_dialog
    ):
        installer = MagicMock()
        installer.ensure = AsyncMock(return_value=True)
        dialog = make_dialog(installer)
        page = MagicMock(spec=ft.Page)

        with patch(
            "chronicler.desktop.views.transcript.recording.list_input_devices", return_value=[]
        ):
            await dialog.run(page)

        page.show_dialog.assert_not_called()
        dialog.show_snackbar.assert_called_once()
        assert "input" in dialog.show_snackbar.call_args[0][0].lower()
