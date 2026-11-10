"""Tests for the record-a-source dialog."""

import asyncio
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


class TestDismissal:
    @pytest.mark.asyncio
    async def test_dismissing_the_dialog_stops_the_recorder_and_removes_the_temp_folder(
        self, make_dialog
    ):
        dialog = make_dialog()
        page = MagicMock(spec=ft.Page)
        device = InputDevice(index=0, name="Mic", channels=1)

        with (
            patch(
                "chronicler.desktop.views.transcript.recording.list_input_devices",
                return_value=[device],
            ),
            patch("chronicler.desktop.views.transcript.recording.Recorder") as recorder_class,
        ):
            recorder = recorder_class.return_value
            recorder.is_recording = False
            recorder.start.side_effect = lambda: setattr(recorder, "is_recording", True)

            task = asyncio.ensure_future(dialog.run(page))
            await asyncio.sleep(0)
            (shown,), _ = page.show_dialog.call_args
            record_button = shown.content.controls[2]
            await record_button.on_click(MagicMock())
            temp_folder = dialog.temp_path.parent
            assert temp_folder.exists()

            shown.on_dismiss(MagicMock())
            await asyncio.wait_for(task, timeout=1)

        recorder.stop.assert_called_once()
        assert not temp_folder.exists()


class TestFailedSave:
    @pytest.mark.asyncio
    async def test_a_failed_save_keeps_the_dialog_open_and_the_recording(self, make_dialog):
        dialog = make_dialog()
        dialog.file_stager.stage.side_effect = OSError("server unreachable")
        page = MagicMock(spec=ft.Page)
        device = InputDevice(index=0, name="Mic", channels=1)

        with (
            patch(
                "chronicler.desktop.views.transcript.recording.list_input_devices",
                return_value=[device],
            ),
            patch("chronicler.desktop.views.transcript.recording.Recorder") as recorder_class,
        ):
            recorder = recorder_class.return_value
            recorder.is_recording = False
            recorder.start.side_effect = lambda: setattr(recorder, "is_recording", True)
            recorder.stop.side_effect = lambda: setattr(recorder, "is_recording", False)

            task = asyncio.ensure_future(dialog.run(page))
            await asyncio.sleep(0)
            (shown,), _ = page.show_dialog.call_args
            await shown.content.controls[2].on_click(MagicMock())
            recording = dialog.temp_path
            recording.write_bytes(b"RIFF")

            await shown.actions[1].on_click(MagicMock())

            assert not task.done()
            page.pop_dialog.assert_not_called()
            assert recording.exists()
            assert "server unreachable" in dialog.show_snackbar.call_args[0][0]

            dialog.file_stager.stage.side_effect = None
            dialog.file_stager.stage.return_value = "staged.wav"
            await shown.actions[1].on_click(MagicMock())
            await asyncio.wait_for(task, timeout=1)

        dialog.chronicle_service.add_audio_source.assert_awaited_once()
        page.pop_dialog.assert_called_once()
        assert not recording.parent.exists()
