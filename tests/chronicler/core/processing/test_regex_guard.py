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
