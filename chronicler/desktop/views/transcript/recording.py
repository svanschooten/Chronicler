"""The record-a-source dialog.

The microphone is on the machine running the UI, so recording always happens client-side.
The finished file goes through the same FileStager the file picker uses, which is what
makes it work identically in full-stack and thin-client mode.
"""

import logging
import tempfile
from collections.abc import Callable
from pathlib import Path

import flet as ft

from chronicler.core.models import Chronicle
from chronicler.core.recording import InputDevice, Recorder, RecordingError, list_input_devices
from chronicler.desktop.dialogs import await_dialog
from chronicler.desktop.theme import ThemeColors
from chronicler.i18n import t

logger = logging.getLogger(__name__)


class RecordingDialog:
    def __init__(
        self,
        chronicle: Chronicle,
        chronicle_service,
        file_stager,
        show_snackbar: Callable[[str], None],
        colors: ThemeColors,
    ):
        self.chronicle = chronicle
        self.chronicle_service = chronicle_service
        self.file_stager = file_stager
        self.show_snackbar = show_snackbar
        self.colors = colors
        self.recorder: Recorder | None = None
        self.temp_path: Path | None = None

    def devices(self) -> list[InputDevice]:
        try:
            return list_input_devices()
        except RecordingError as error:
            logger.warning(f"No input devices available: {error}")
            self.show_snackbar(str(error))
            return []

    async def run(self, page: ft.Page) -> None:
        devices = self.devices()
        if not devices:
            return

        device_field = ft.Dropdown(
            label=t("recording.device"),
            value=str(devices[0].index),
            options=[
                ft.DropdownOption(key=str(device.index), text=device.label) for device in devices
            ],
        )
        name_field = ft.TextField(label=t("recording.name"), value=t("recording.default_name"))
        status = ft.Text(t("recording.ready"), size=12, color=self.colors.muted)
        record_button = ft.FilledButton(t("recording.start"))

        async def toggle(_event):
            if self.recorder is None or not self.recorder.is_recording:
                await self._start(int(device_field.value), status, record_button, device_field)
            else:
                await self._stop(status, record_button)

        record_button.on_click = toggle

        def build(on_choice) -> ft.AlertDialog:
            async def finish(_event):
                await self._finish(name_field.value)
                on_choice(lambda: None)
                page.pop_dialog()

            return ft.AlertDialog(
                title=ft.Text(t("recording.title")),
                content=ft.Column(
                    [device_field, name_field, record_button, status], tight=True, width=420
                ),
                actions=[
                    ft.TextButton(t("common.cancel"), on_click=on_choice(lambda: None)),
                    ft.FilledButton(t("recording.save"), on_click=finish),
                ],
            )

        await await_dialog(page, build)
        if self.recorder is not None and self.recorder.is_recording:
            self.recorder.stop()

    async def _start(self, device_index, status, button, device_field) -> None:
        self.temp_path = Path(tempfile.mkdtemp(prefix="chronicler-rec-")) / "recording.wav"
        self.recorder = Recorder(self.temp_path, device=device_index)
        try:
            self.recorder.start()
        except RecordingError as error:
            self.show_snackbar(str(error))
            return

        status.value = t("recording.recording")
        button.text = t("recording.stop")
        device_field.disabled = True
        _refresh(status, button, device_field)

    async def _stop(self, status, button) -> None:
        if self.recorder is None:
            return
        try:
            self.recorder.stop()
        except RecordingError as error:
            self.show_snackbar(str(error))
            return
        status.value = t("recording.recorded", seconds=int(self.recorder.seconds_recorded))
        button.text = t("recording.start")
        _refresh(status, button)

    async def _finish(self, name: str) -> None:
        if self.recorder is not None and self.recorder.is_recording:
            self.recorder.stop()
        if self.temp_path is None or not self.temp_path.exists():
            return

        filename = (name or t("recording.default_name")).strip()
        if not filename.lower().endswith(".wav"):
            filename = f"{filename}.wav"

        try:
            staged = await self.file_stager.stage(str(self.temp_path))
            await self.chronicle_service.add_audio_source(self.chronicle.id, staged, filename)
        except Exception as error:
            logger.exception("Could not store the recording")
            self.show_snackbar(t("recording.failed", error=error))
            return

        self.show_snackbar(t("recording.saved", name=filename))


def _refresh(*controls: ft.Control) -> None:
    for control in controls:
        try:
            control.update()
        except (RuntimeError, AssertionError):
            pass
