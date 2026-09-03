"""Capturing audio from a local input device."""

import logging
import queue
import threading
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chronicler.core import extras

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHANNELS = 1
BLOCK_SIZE = 1600


class RecordingError(RuntimeError):
    """Recording could not start, or failed while running."""


@dataclass(frozen=True)
class InputDevice:
    index: int
    name: str
    channels: int

    @property
    def label(self) -> str:
        return f"{self.name} ({self.index})"


def _sounddevice() -> Any:
    try:
        import sounddevice
    except (ImportError, OSError) as error:
        raise RecordingError(extras.missing_message("recording", error)) from error
    return sounddevice


def list_input_devices() -> list[InputDevice]:
    """Every device that can capture, in the order the audio backend reports them."""
    sounddevice = _sounddevice()
    devices = []
    for index, info in enumerate(sounddevice.query_devices()):
        channels = int(info.get("max_input_channels", 0))
        if channels > 0:
            devices.append(
                InputDevice(
                    index=index, name=str(info.get("name", f"Device {index}")), channels=channels
                )
            )
    return devices


class Recorder:
    """
    Records 16 kHz mono audio to a WAV file until stopped.

    The microphone is always on the machine running the UI, so this runs client-side in
    every deployment mode; a thin client hands the finished file to the same FileStager
    the file picker uses. See docs/recording.md.
    """

    def __init__(self, destination: Path, device: int | None = None):
        self.destination = destination
        self.device = device
        self._queue: queue.Queue = queue.Queue()
        self._stream: Any = None
        self._writer: threading.Thread | None = None
        self._running = False
        self._error: Exception | None = None
        self._frames = 0

    @property
    def is_recording(self) -> bool:
        return self._running

    @property
    def seconds_recorded(self) -> float:
        return self._frames / SAMPLE_RATE

    def start(self) -> None:
        if self._running:
            raise RecordingError("Already recording")

        sounddevice = _sounddevice()
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        self._running = True
        self._frames = 0
        self._error = None

        def on_audio(indata, _frames, _time, status):
            if status:
                logger.debug(f"Audio input status: {status}")
            self._queue.put(bytes(indata))

        try:
            self._stream = sounddevice.RawInputStream(
                samplerate=SAMPLE_RATE,
                blocksize=BLOCK_SIZE,
                device=self.device,
                dtype="int16",
                channels=CHANNELS,
                callback=on_audio,
            )
            self._stream.start()
        except Exception as error:
            self._running = False
            raise RecordingError(f"Could not open the input device: {error}") from error

        self._writer = threading.Thread(target=self._write_loop, daemon=True)
        self._writer.start()
        logger.info(f"Recording to {self.destination.name}")

    def _write_loop(self) -> None:
        try:
            with wave.open(str(self.destination), "wb") as handle:
                handle.setnchannels(CHANNELS)
                handle.setsampwidth(2)
                handle.setframerate(SAMPLE_RATE)
                while self._running or not self._queue.empty():
                    try:
                        block = self._queue.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    handle.writeframes(block)
                    self._frames += len(block) // 2
        except Exception as error:
            self._error = error
            logger.exception("Recording writer failed")

    def stop(self) -> Path:
        """Stops and returns the finished file."""
        if not self._running:
            raise RecordingError("Not recording")

        self._running = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if self._writer is not None:
            self._writer.join(timeout=10)
            self._writer = None

        if self._error is not None:
            raise RecordingError(f"Recording failed: {self._error}") from self._error
        logger.info(f"Recorded {self.seconds_recorded:.1f}s to {self.destination.name}")
        return self.destination
