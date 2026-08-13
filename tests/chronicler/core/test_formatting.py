import pytest

from chronicler.core.formatting import format_duration, format_timestamp, parse_timestamp


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (0, "0s"),
        (12, "12s"),
        (59, "59s"),
        (60, "1m 0s"),
        (72, "1m 12s"),
        (3599, "59m 59s"),
        (3600, "1h 0m"),
        (5025, "1h 23m"),  # seconds within the hour are dropped once hours show
    ],
)
def test_format_duration(seconds, expected):
    assert format_duration(seconds) == expected


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (0, "00:00:00"),
        (5, "00:00:05"),
        (65, "00:01:05"),
        (3661, "01:01:01"),
    ],
)
def test_format_timestamp(seconds, expected):
    assert format_timestamp(seconds) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("00:00:00", 0.0),
        ("00:01:05", 65.0),
        ("01:01:01", 3661.0),
        ("01:05", 65.0),  # MM:SS, no hours
        ("00:01:05.500", 65.5),
    ],
)
def test_parse_timestamp(text, expected):
    assert parse_timestamp(text) == expected


@pytest.mark.parametrize("text", ["not a timestamp", "1:2:3:4", "ab:cd:ef", ""])
def test_parse_timestamp_rejects_malformed_input(text):
    with pytest.raises(ValueError, match="timestamp"):
        parse_timestamp(text)


def test_format_and_parse_timestamp_round_trip():
    for seconds in (0, 5, 65, 3661, 86399):
        assert parse_timestamp(format_timestamp(seconds)) == seconds
