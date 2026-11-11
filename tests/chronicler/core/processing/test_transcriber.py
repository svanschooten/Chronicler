"""Tests for the faster-whisper wrapper."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from chronicler.core.processing.transcriber import transcribe_audio


def _stub_model(*segments):
    """A stand-in for WhisperModel: `transcribe` returns (segments, info)."""
    return SimpleNamespace(
        transcribe=lambda _path, **_kwargs: (
            [SimpleNamespace(text=text, start=start, end=end) for text, start, end in segments],
            SimpleNamespace(),
        )
    )


def test_transcribe_audio_labels_segments_with_the_requested_speaker():
    """
    One audio source is one participant's own track, and the caller knows whose before
    transcription starts - so the segments come back already labelled, rather than carrying
    a placeholder for the caller to overwrite afterwards.
    """
    model = _stub_model(("Hello there", 0.0, 1.0), ("General Kenobi", 1.0, 2.0))

    with patch("chronicler.core.processing.transcriber._get_model", return_value=model):
        lines = transcribe_audio("/tmp/alice.mp3", "Alice")

    assert [line.speaker_name for line in lines] == ["Alice", "Alice"]
    assert [line.text for line in lines] == ["Hello there", "General Kenobi"]
    assert [(line.start_time, line.end_time) for line in lines] == [(0.0, 1.0), (1.0, 2.0)]


def test_transcribe_audio_skips_empty_segments():
    model = _stub_model(("Hello", 0.0, 1.0), ("   ", 1.0, 2.0))

    with patch("chronicler.core.processing.transcriber._get_model", return_value=model):
        lines = transcribe_audio("/tmp/alice.mp3", "Alice")

    assert [line.text for line in lines] == ["Hello"]


def _timed_model(duration, *segments):
    model = _stub_model(*segments)
    inner = model.transcribe
    model.transcribe = lambda path, **kwargs: (
        inner(path, **kwargs)[0],
        SimpleNamespace(duration=duration),
    )
    return model


def test_transcribe_audio_reports_the_fraction_done_after_each_segment():
    model = _timed_model(4.0, ("One", 0.0, 1.0), ("Two", 1.0, 3.0), ("Three", 3.0, 4.0))
    seen: list[float] = []

    with patch("chronicler.core.processing.transcriber._get_model", return_value=model):
        transcribe_audio("/tmp/alice.mp3", "Alice", on_progress=seen.append)

    assert seen == [0.25, 0.75, 1.0]


def test_a_cancelled_task_stops_between_segments():
    import threading

    from chronicler.core.cancellation import TaskCancelledError, cancel_event

    model = _timed_model(3.0, ("One", 0.0, 1.0), ("Two", 1.0, 2.0), ("Three", 2.0, 3.0))
    flag = threading.Event()
    token = cancel_event.set(flag)
    seen: list[float] = []

    def on_progress(fraction):
        seen.append(fraction)
        flag.set()  # cancelled while the first segment was being reported

    try:
        with (
            patch("chronicler.core.processing.transcriber._get_model", return_value=model),
            pytest.raises(TaskCancelledError),
        ):
            transcribe_audio("/tmp/alice.mp3", "Alice", on_progress=on_progress)
    finally:
        cancel_event.reset(token)

    assert len(seen) == 1
