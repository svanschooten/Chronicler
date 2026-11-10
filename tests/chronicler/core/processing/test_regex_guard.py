import asyncio
import time

import pytest

from chronicler.core.processing import regex_guard
from chronicler.core.processing.importers import RegexImporter
from chronicler.core.processing.regex_guard import (
    MAX_PATTERN_LENGTH,
    PatternTimeoutError,
    UnsafePatternError,
    assert_safe_pattern,
    compile_pattern,
    run_timed,
)

ORDINARY_PATTERNS = [
    r"^(\w+( \w+)*):(.*)$",
    r"^([A-Z][a-z]+(?: [A-Z][a-z]+)*):\s*(.*)$",
    r"^\s*(.*?)\s*:\s*(.*?)\s*$",
    r"^([A-Za-z0-9 _]+)\s*:(.*)$",
    r".*",
    r"(cat|dog)+",
]

# Slow enough to hit a short timeout even with the `regex` package.
SLOW_PATTERN = r"(\w+\s?)*$"
SLOW_LINE = "a" * 5000 + "!"

CATASTROPHIC_PATTERNS = [r"(a+)+$", r"(x+x+)+y", r"^(a|a?)+$", r"(.*a){20}"]


@pytest.mark.parametrize("pattern", ORDINARY_PATTERNS + CATASTROPHIC_PATTERNS)
def test_accepts_every_pattern_that_is_valid_and_short(pattern):
    assert_safe_pattern(pattern)


def test_rejects_overlong_pattern():
    with pytest.raises(UnsafePatternError):
        assert_safe_pattern("a" * (MAX_PATTERN_LENGTH + 1))


def test_rejects_invalid_regex_syntax():
    with pytest.raises(UnsafePatternError):
        assert_safe_pattern("(unclosed")


@pytest.mark.parametrize("pattern", CATASTROPHIC_PATTERNS)
def test_catastrophic_patterns_finish_quickly_on_adversarial_lines(pattern):
    compiled = compile_pattern(pattern)
    started = time.monotonic()
    try:
        run_timed(compiled, compiled.search, "a" * 40 + "!")
    except PatternTimeoutError:
        pass
    assert time.monotonic() - started < regex_guard.MATCH_TIMEOUT_SECONDS + 2


def test_a_slow_match_raises_a_timeout_error(monkeypatch):
    monkeypatch.setattr(regex_guard, "MATCH_TIMEOUT_SECONDS", 0.05)
    compiled = compile_pattern(SLOW_PATTERN)
    with pytest.raises(PatternTimeoutError, match="Simplify"):
        run_timed(compiled, compiled.search, SLOW_LINE)


@pytest.mark.asyncio
async def test_slow_import_does_not_stall_the_event_loop(monkeypatch):
    monkeypatch.setattr(regex_guard, "MATCH_TIMEOUT_SECONDS", 0.3)
    importer = RegexImporter(SLOW_PATTERN)
    content = "a" * 30000 + "!"

    longest_stall = 0.0

    async def ticker():
        nonlocal longest_stall
        last = time.monotonic()
        while True:
            await asyncio.sleep(0.01)
            now = time.monotonic()
            longest_stall = max(longest_stall, now - last)
            last = now

    task = asyncio.create_task(ticker())
    try:
        with pytest.raises(PatternTimeoutError):
            await asyncio.to_thread(importer.parse, content)
    finally:
        task.cancel()
    assert longest_stall < 0.5


class TestTimeLimit:
    """One budget for every match an import or clean makes, not just each match on its own."""

    def test_matches_inside_a_time_limit_share_its_deadline(self, monkeypatch):
        monkeypatch.setattr(regex_guard, "MATCH_TIMEOUT_SECONDS", 5.0)
        compiled = compile_pattern(SLOW_PATTERN)

        started = time.monotonic()
        with pytest.raises(PatternTimeoutError, match="whole transcript"):
            with regex_guard.time_limit(0.2):
                for _ in range(100):
                    run_timed(compiled, compiled.search, SLOW_LINE)
        assert time.monotonic() - started < 2

    def test_a_spent_budget_refuses_the_next_match_without_running_it(self):
        compiled = compile_pattern(r"a")
        with regex_guard.time_limit(0):
            with pytest.raises(PatternTimeoutError, match="whole transcript"):
                run_timed(compiled, compiled.search, "a")

    def test_a_nested_limit_keeps_the_earlier_deadline(self):
        compiled = compile_pattern(r"a")
        with regex_guard.time_limit(0):
            with regex_guard.time_limit(60):
                with pytest.raises(PatternTimeoutError):
                    run_timed(compiled, compiled.search, "a")

    def test_outside_a_time_limit_only_the_per_match_bound_applies(self):
        compiled = compile_pattern(r"a")
        assert run_timed(compiled, compiled.search, "a") is not None

    def test_an_import_stops_at_its_total_budget(self, monkeypatch):
        monkeypatch.setattr(regex_guard, "MATCH_TIMEOUT_SECONDS", 5.0)
        monkeypatch.setattr(regex_guard, "TOTAL_TIMEOUT_SECONDS", 0.2)
        importer = RegexImporter(SLOW_PATTERN)

        started = time.monotonic()
        with pytest.raises(PatternTimeoutError, match="whole transcript"):
            importer.parse("\n".join([SLOW_LINE] * 100))
        assert time.monotonic() - started < 2

    def test_a_clean_stops_at_its_total_budget(self, monkeypatch):
        from chronicler.core.config_sections import CleaningSettings
        from chronicler.core.models import TranscriptLine
        from chronicler.core.processing.cleaners import TranscriptCleaner

        monkeypatch.setattr(regex_guard, "MATCH_TIMEOUT_SECONDS", 5.0)
        monkeypatch.setattr(regex_guard, "TOTAL_TIMEOUT_SECONDS", 0.2)
        lines = [
            TranscriptLine(speaker_name="A", text=SLOW_LINE, start_time=i, end_time=i + 1)
            for i in range(100)
        ]
        cleaner = TranscriptCleaner(CleaningSettings(strip_patterns=[SLOW_PATTERN]))

        started = time.monotonic()
        with pytest.raises(PatternTimeoutError, match="whole transcript"):
            cleaner.clean(lines)
        assert time.monotonic() - started < 2
