import pytest

from chronicler.core.models import TranscriptLine
from chronicler.core.services.srt import NoRealTimestampsError, format_srt, srt_timestamp


def line(text, start, end, speaker="GM"):
    return TranscriptLine(speaker_name=speaker, text=text, start_time=start, end_time=end)


class TestSrtTimestamp:
    @pytest.mark.parametrize(
        "seconds,expected",
        [
            (0.0, "00:00:00,000"),
            (1.5, "00:00:01,500"),
            (61.25, "00:01:01,250"),
            (3661.001, "01:01:01,001"),
            (3600.0, "01:00:00,000"),
        ],
    )
    def test_formats_as_hours_minutes_seconds_milliseconds(self, seconds, expected):
        assert srt_timestamp(seconds) == expected

    def test_milliseconds_are_truncated_not_rounded_up_past_a_second(self):
        assert srt_timestamp(0.9999) == "00:00:00,999"

    def test_negative_times_clamp_to_zero(self):
        assert srt_timestamp(-5.0) == "00:00:00,000"


class TestFormatSrt:
    def test_produces_numbered_cues(self):
        output = format_srt([line("Hello", 0.0, 1.0), line("World", 1.0, 2.0)])

        assert output == (
            "1\n"
            "00:00:00,000 --> 00:00:01,000\n"
            "GM: Hello\n"
            "\n"
            "2\n"
            "00:00:01,000 --> 00:00:02,000\n"
            "GM: World\n"
        )

    def test_speaker_prefix_can_be_omitted(self):
        output = format_srt([line("Hello", 0.0, 1.0)], include_speaker=False)

        assert "GM:" not in output
        assert "Hello" in output

    def test_an_unknown_speaker_is_labelled(self):
        unknown = TranscriptLine(text="Hello", start_time=0.0, end_time=1.0)

        assert "Unknown: Hello" in format_srt([unknown])

    def test_blank_lines_are_skipped_and_numbering_stays_contiguous(self):
        output = format_srt([line("One", 0.0, 1.0), line("   ", 1.0, 2.0), line("Two", 2.0, 3.0)])

        assert "\n1\n" not in output[1:]
        assert output.startswith("1\n")
        assert "\n2\n" in output
        assert "\n3\n" not in output

    def test_internal_newlines_are_preserved_as_cue_lines(self):
        output = format_srt([line("First\nSecond", 0.0, 1.0)])

        assert "GM: First\nSecond\n" in output

    def test_a_zero_length_cue_is_given_a_minimum_duration(self):
        output = format_srt([line("Blip", 5.0, 5.0)])

        assert "00:00:05,000 --> 00:00:05,500" in output

    def test_an_end_before_its_start_is_corrected(self):
        output = format_srt([line("Backwards", 5.0, 2.0)])

        assert "00:00:05,000 --> 00:00:05,500" in output

    def test_empty_input_produces_empty_output(self):
        assert format_srt([]) == ""


class TestSyntheticTimestampGuard:
    def test_index_based_timestamps_are_refused(self):
        lines = [line("One", 0.0, 1.0), line("Two", 1.0, 2.0), line("Three", 2.0, 3.0)]

        with pytest.raises(NoRealTimestampsError):
            format_srt(lines, require_real_timestamps=True)

    def test_real_timestamps_are_accepted(self):
        lines = [line("One", 0.0, 2.4), line("Two", 2.4, 5.9)]

        assert format_srt(lines, require_real_timestamps=True)

    def test_a_single_line_is_not_judged_synthetic(self):
        assert format_srt([line("Only", 0.0, 1.0)], require_real_timestamps=True)

    def test_the_guard_is_off_by_default(self):
        lines = [line("One", 0.0, 1.0), line("Two", 1.0, 2.0), line("Three", 2.0, 3.0)]

        assert format_srt(lines)
