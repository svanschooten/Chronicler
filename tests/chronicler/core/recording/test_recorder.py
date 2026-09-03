import sys
import wave
from unittest.mock import MagicMock, patch

import pytest

from chronicler.core.recording import (
    InputDevice,
    Recorder,
    RecordingError,
    list_input_devices,
)


class FakeStream:
    """Stands in for a RawInputStream, feeding fixed blocks to the callback."""

    def __init__(self, blocks=None, **kwargs):
        self.callback = kwargs["callback"]
        self.blocks = blocks if blocks is not None else [b"\x01\x00" * 800]
        self.started = False
        self.closed = False

    def start(self):
        self.started = True
        for block in self.blocks:
            self.callback(block, len(block) // 2, None, None)

    def stop(self):
        self.started = False

    def close(self):
        self.closed = True


def fake_sounddevice(blocks=None, devices=None, raise_on_open=None):
    module = MagicMock()
    module.query_devices.return_value = (
        devices
        if devices is not None
        else [
            {"name": "Built-in Mic", "max_input_channels": 2},
            {"name": "Speakers", "max_input_channels": 0},
            {"name": "USB Interface", "max_input_channels": 1},
        ]
    )
    if raise_on_open:
        module.RawInputStream.side_effect = raise_on_open
    else:
        module.RawInputStream.side_effect = lambda **kwargs: FakeStream(blocks, **kwargs)
    return module


class TestListInputDevices:
    def test_only_capture_devices_are_listed(self):
        with patch.dict(sys.modules, {"sounddevice": fake_sounddevice()}):
            devices = list_input_devices()

        assert [device.name for device in devices] == ["Built-in Mic", "USB Interface"]

    def test_devices_keep_their_backend_index(self):
        with patch.dict(sys.modules, {"sounddevice": fake_sounddevice()}):
            devices = list_input_devices()

        assert [device.index for device in devices] == [0, 2]

    def test_a_label_identifies_the_device(self):
        assert InputDevice(index=2, name="USB", channels=1).label == "USB (2)"

    def test_a_missing_extra_is_reported_clearly(self):
        with patch.dict(sys.modules, {"sounddevice": None}):
            with pytest.raises(RecordingError, match="recording"):
                list_input_devices()


class TestRecorder:
    def test_writes_a_wav_file(self, tmp_path):
        destination = tmp_path / "take.wav"
        with patch.dict(sys.modules, {"sounddevice": fake_sounddevice()}):
            recorder = Recorder(destination)
            recorder.start()
            result = recorder.stop()

        assert result == destination
        with wave.open(str(destination)) as handle:
            assert handle.getnchannels() == 1
            assert handle.getframerate() == 16000
            assert handle.getnframes() > 0

    def test_it_records_the_expected_amount(self, tmp_path):
        blocks = [b"\x01\x00" * 1600] * 10
        with patch.dict(sys.modules, {"sounddevice": fake_sounddevice(blocks)}):
            recorder = Recorder(tmp_path / "take.wav")
            recorder.start()
            recorder.stop()

            assert recorder.seconds_recorded == pytest.approx(1.0, abs=0.05)

    def test_the_chosen_device_is_used(self, tmp_path):
        module = fake_sounddevice()
        with patch.dict(sys.modules, {"sounddevice": module}):
            recorder = Recorder(tmp_path / "take.wav", device=2)
            recorder.start()
            recorder.stop()

        assert module.RawInputStream.call_args.kwargs["device"] == 2

    def test_is_recording_reflects_state(self, tmp_path):
        with patch.dict(sys.modules, {"sounddevice": fake_sounddevice()}):
            recorder = Recorder(tmp_path / "take.wav")
            assert recorder.is_recording is False
            recorder.start()
            assert recorder.is_recording is True
            recorder.stop()
            assert recorder.is_recording is False

    def test_starting_twice_is_refused(self, tmp_path):
        with patch.dict(sys.modules, {"sounddevice": fake_sounddevice()}):
            recorder = Recorder(tmp_path / "take.wav")
            recorder.start()
            try:
                with pytest.raises(RecordingError, match="Already recording"):
                    recorder.start()
            finally:
                recorder.stop()

    def test_stopping_without_starting_is_refused(self, tmp_path):
        with patch.dict(sys.modules, {"sounddevice": fake_sounddevice()}):
            with pytest.raises(RecordingError, match="Not recording"):
                Recorder(tmp_path / "take.wav").stop()

    def test_a_device_that_cannot_open_is_reported(self, tmp_path):
        module = fake_sounddevice(raise_on_open=OSError("device busy"))
        with patch.dict(sys.modules, {"sounddevice": module}):
            recorder = Recorder(tmp_path / "take.wav")

            with pytest.raises(RecordingError, match="input device"):
                recorder.start()

            assert recorder.is_recording is False

    def test_the_destination_directory_is_created(self, tmp_path):
        destination = tmp_path / "nested" / "deeper" / "take.wav"
        with patch.dict(sys.modules, {"sounddevice": fake_sounddevice()}):
            recorder = Recorder(destination)
            recorder.start()
            recorder.stop()

        assert destination.exists()
