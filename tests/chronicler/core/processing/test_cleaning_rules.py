import uuid

import pytest

from chronicler.core.config_sections import CleaningSettings
from chronicler.core.models import TranscriptLine
from chronicler.core.processing.cleaners import (
    CollapseWhitespace,
    DropDuplicateSegments,
    DropEmpty,
    DropHallucinations,
    DropRepeats,
    DropShortLines,
    MergeSameSpeaker,
    StripPatterns,
    TranscriptCleaner,
    build_pipeline,
)

GM = uuid.uuid4()
PLAYER = uuid.uuid4()


def line(text, start=0.0, end=1.0, speaker="GM", speaker_id=GM):
    return TranscriptLine(
        speaker_id=speaker_id, speaker_name=speaker, text=text, start_time=start, end_time=end
    )


def texts(lines):
    return [line.text for line in lines]


class TestCollapseWhitespace:
    def test_collapses_runs_and_strips(self):
        result = CollapseWhitespace().apply([line("  Hello   world  ")])

        assert texts(result) == ["Hello world"]

    def test_flattens_embedded_newlines(self):
        result = CollapseWhitespace().apply([line("Hello\n   world")])

        assert texts(result) == ["Hello world"]

    def test_leaves_the_input_lines_untouched(self):
        original = line("  spaced  ")
        CollapseWhitespace().apply([original])

        assert original.text == "  spaced  "


class TestStripPatterns:
    def test_removes_matching_fragments(self):
        result = StripPatterns([r"\[[^\]]*\]"]).apply([line("Hello [laughs] world")])

        assert texts(result) == ["Hello  world"]

    def test_applies_every_pattern(self):
        result = StripPatterns([r"\[.*?\]", r"\(.*?\)"]).apply([line("a [x] b (y) c")])

        assert texts(result) == ["a  b  c"]

    def test_no_patterns_is_a_passthrough(self):
        result = StripPatterns([]).apply([line("untouched")])

        assert texts(result) == ["untouched"]


class TestDropEmpty:
    def test_drops_blank_and_whitespace_only_lines(self):
        result = DropEmpty().apply([line("keep"), line(""), line("   ")])

        assert texts(result) == ["keep"]


class TestDropHallucinations:
    def test_normalized_match_ignores_case_and_trailing_punctuation(self):
        rule = DropHallucinations(["you"], "normalized")
        result = rule.apply([line("You."), line("you"), line("YOU!"), line("you there")])

        assert texts(result) == ["you there"]

    def test_exact_match_is_literal(self):
        rule = DropHallucinations(["you"], "exact")
        result = rule.apply([line("you"), line("You."), line("YOU")])

        assert texts(result) == ["You.", "YOU"]

    def test_regex_match_must_cover_the_whole_line(self):
        rule = DropHallucinations([r"Ondertiteling door.*"], "regex")
        result = rule.apply(
            [line("Ondertiteling door de Amara.org gemeenschap"), line("En Ondertiteling door X")]
        )

        assert texts(result) == ["En Ondertiteling door X"]

    def test_regex_match_is_case_insensitive(self):
        rule = DropHallucinations([r"thanks for watching!?"], "regex")
        result = rule.apply([line("Thanks for watching!"), line("keep")])

        assert texts(result) == ["keep"]

    def test_punctuation_only_phrases_drop_punctuation_only_lines(self):
        rule = DropHallucinations(["..."], "normalized")
        result = rule.apply([line("..."), line("."), line("real")])

        assert texts(result) == ["real"]

    def test_an_empty_phrase_list_drops_nothing(self):
        result = DropHallucinations([], "normalized").apply([line("you")])

        assert texts(result) == ["you"]


class TestDropShortLines:
    def test_drops_lines_below_the_threshold(self):
        result = DropShortLines(3).apply([line("ab"), line("abc"), line("abcd")])

        assert texts(result) == ["abc", "abcd"]

    def test_zero_keeps_everything(self):
        result = DropShortLines(0).apply([line("a")])

        assert texts(result) == ["a"]

    def test_length_is_measured_after_stripping(self):
        result = DropShortLines(3).apply([line("  ab  ")])

        assert texts(result) == []


class TestDropDuplicateSegments:
    def test_drops_identical_text_at_the_same_rounded_times(self):
        result = DropDuplicateSegments().apply(
            [line("same", 1.0, 2.0), line("same", 1.2, 2.1), line("same", 9.0, 10.0)]
        )

        assert [(line.text, line.start_time) for line in result] == [("same", 1.0), ("same", 9.0)]

    def test_different_speakers_are_not_duplicates(self):
        result = DropDuplicateSegments().apply(
            [
                line("same", 1.0, 2.0),
                line("same", 1.0, 2.0, speaker="Player", speaker_id=PLAYER),
            ]
        )

        assert len(result) == 2


class TestDropRepeats:
    def test_drops_a_repeat_inside_the_window(self):
        result = DropRepeats(200.0).apply(
            [line("hello", 0.0, 1.0), line("hello", 50.0, 51.0), line("hello", 80.0, 81.0)]
        )

        assert [line.start_time for line in result] == [0.0]

    def test_keeps_a_repeat_beyond_the_window(self):
        result = DropRepeats(200.0).apply([line("hello", 0.0, 1.0), line("hello", 500.0, 501.0)])

        assert [line.start_time for line in result] == [0.0, 500.0]

    def test_the_window_runs_from_the_last_kept_line(self):
        result = DropRepeats(100.0).apply(
            [line("x", 0.0, 1.0), line("x", 90.0, 91.0), line("x", 180.0, 181.0)]
        )

        assert [line.start_time for line in result] == [0.0, 180.0]

    def test_repeats_are_tracked_per_speaker(self):
        result = DropRepeats(200.0).apply(
            [
                line("hello", 0.0, 1.0),
                line("hello", 10.0, 11.0, speaker="Player", speaker_id=PLAYER),
            ]
        )

        assert len(result) == 2

    def test_comparison_ignores_case_and_punctuation(self):
        result = DropRepeats(200.0).apply([line("Hello.", 0.0, 1.0), line("hello", 10.0, 11.0)])

        assert len(result) == 1

    def test_a_zero_window_drops_nothing(self):
        result = DropRepeats(0.0).apply([line("x", 0.0, 1.0), line("x", 0.0, 1.0)])

        assert len(result) == 2


class TestMergeSameSpeaker:
    def test_merges_consecutive_turns_and_spans_the_times(self):
        result = MergeSameSpeaker().apply(
            [line("nice", 0.0, 1.0), line("okay", 1.0, 2.0), line("done", 2.0, 3.0)]
        )

        assert texts(result) == ["nice okay done"]
        assert result[0].start_time == 0.0
        assert result[0].end_time == 3.0

    def test_a_different_speaker_breaks_the_run(self):
        result = MergeSameSpeaker().apply(
            [
                line("Hello", 0.0, 1.0),
                line("world", 1.0, 2.0),
                line("Hi", 2.0, 3.0, speaker="Player", speaker_id=PLAYER),
            ]
        )

        assert texts(result) == ["Hello world", "Hi"]

    def test_does_not_mutate_the_input(self):
        first = line("nice", 0.0, 1.0)
        MergeSameSpeaker().apply([first, line("okay", 1.0, 2.0)])

        assert first.text == "nice"


class TestPipelineComposition:
    def test_defaults_enable_the_expected_rules(self):
        rules = build_pipeline(CleaningSettings())
        kinds = [type(rule).__name__ for rule in rules]

        assert kinds == [
            "CollapseWhitespace",
            "StripPatterns",
            "DropEmpty",
            "DropHallucinations",
            "DropShortLines",
            "DropDuplicateSegments",
            "DropRepeats",
            "MergeSameSpeaker",
        ]

    def test_disabled_rules_are_left_out(self):
        settings = CleaningSettings(
            collapse_whitespace=False,
            drop_hallucinations=False,
            drop_repeats=False,
            drop_duplicate_segments=False,
            merge_same_speaker=False,
        )
        kinds = [type(rule).__name__ for rule in build_pipeline(settings)]

        assert kinds == ["StripPatterns", "DropEmpty", "DropShortLines"]

    def test_everything_disabled_is_a_passthrough(self):
        settings = CleaningSettings(
            collapse_whitespace=False,
            drop_hallucinations=False,
            drop_repeats=False,
            drop_duplicate_segments=False,
            merge_same_speaker=False,
        )
        cleaner = TranscriptCleaner(settings)
        original = [line("  keep  me  ")]

        assert texts(cleaner.clean(original)) == ["  keep  me  "]


class TestTranscriptCleaner:
    def test_empty_input(self):
        assert TranscriptCleaner().clean([]) == []

    def test_default_settings_are_used_when_none_given(self):
        cleaned = TranscriptCleaner().clean([line("  Hello   world  ")])

        assert texts(cleaned) == ["Hello world"]

    def test_the_whisper_silence_artifact_is_removed_by_default(self):
        cleaned = TranscriptCleaner().clean(
            [line("Real content here.", 0.0, 1.0), line("You.", 1.0, 2.0)]
        )

        assert texts(cleaned) == ["Real content here."]

    def test_a_looping_repeat_is_collapsed_by_default(self):
        cleaned = TranscriptCleaner().clean(
            [
                line("Okay so.", 0.0, 1.0),
                line("breathing", 2.0, 3.0),
                line("breathing", 4.0, 5.0),
                line("breathing", 6.0, 7.0),
            ]
        )

        assert texts(cleaned) == ["Okay so. breathing"]

    def test_a_dutch_phrase_list_replaces_the_english_default(self):
        settings = CleaningSettings(hallucination_phrases=["Ondertiteling door"])
        cleaned = TranscriptCleaner(settings).clean(
            [line("Ondertiteling door", 0.0, 1.0), line("You.", 1.0, 2.0)]
        )

        assert texts(cleaned) == ["You."]

    def test_speaker_identity_survives_cleaning(self):
        cleaned = TranscriptCleaner().clean([line("nice", 0.0, 1.0), line("okay", 1.0, 2.0)])

        assert cleaned[0].speaker_id == GM
        assert cleaned[0].speaker_name == "GM"

    @pytest.mark.parametrize("rule", [CollapseWhitespace(), DropEmpty(), MergeSameSpeaker()])
    def test_every_rule_handles_an_empty_transcript(self, rule):
        assert rule.apply([]) == []
