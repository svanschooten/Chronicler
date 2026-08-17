import uuid

from chronicler.core.models import TranscriptLine
from chronicler.core.processing.cleaners import TranscriptCleaner


def test_cleaner_merges_consecutive_lines():
    cleaner = TranscriptCleaner()
    speaker_id = uuid.uuid4()
    lines = [
        TranscriptLine(
            speaker_id=speaker_id, speaker_name="GM", text="nice", start_time=0.0, end_time=1.0
        ),
        TranscriptLine(
            speaker_id=speaker_id, speaker_name="GM", text="okay", start_time=1.0, end_time=2.0
        ),
        TranscriptLine(
            speaker_id=speaker_id,
            speaker_name="GM",
            text="I am the sound",
            start_time=2.0,
            end_time=3.0,
        ),
    ]
    cleaned = cleaner.clean(lines)
    assert len(cleaned) == 1
    assert cleaned[0].speaker_name == "GM"
    assert cleaned[0].text == "nice okay I am the sound"
    assert cleaned[0].start_time == 0.0
    assert cleaned[0].end_time == 3.0


def test_cleaner_handles_different_speakers():
    cleaner = TranscriptCleaner()
    s1 = uuid.uuid4()
    s2 = uuid.uuid4()
    lines = [
        TranscriptLine(
            speaker_id=s1, speaker_name="S1", text="Hello", start_time=0.0, end_time=1.0
        ),
        TranscriptLine(
            speaker_id=s1, speaker_name="S1", text="world", start_time=1.0, end_time=2.0
        ),
        TranscriptLine(speaker_id=s2, speaker_name="S2", text="Hi", start_time=2.0, end_time=3.0),
    ]
    cleaned = cleaner.clean(lines)
    assert len(cleaned) == 2
    assert cleaned[0].text == "Hello world"
    assert cleaned[1].text == "Hi"


def test_cleaner_normalizes_whitespace():
    cleaner = TranscriptCleaner()
    s1 = uuid.uuid4()
    lines = [
        TranscriptLine(
            speaker_id=s1, speaker_name="S1", text="  Hello   world  ", start_time=0.0, end_time=1.0
        ),
    ]
    cleaned = cleaner.clean(lines)
    assert cleaned[0].text == "Hello world"
