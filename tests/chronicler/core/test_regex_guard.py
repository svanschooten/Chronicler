import pytest

from chronicler.core.processing.regex_guard import (
    MAX_PATTERN_LENGTH,
    UnsafePatternError,
    assert_safe_pattern,
)

CATASTROPHIC_PATTERNS = [
    r"(a+)+$",
    r"(a*)*$",
    r"(a|a)*$",
    r"(a+)*b$",
    r"(a|aa)+$",
    r"([a-z]+)*$",
    r"(a?)*$",
    r"((a+)+)+$",
]

LEGITIMATE_PATTERNS = [
    r"^([A-Za-z0-9 _]+)\s*:(.*)$",  # DefaultImporter's actual pattern
    r"^([A-Za-z]+):\s*(.*)$",
    r"^\[INFO\] ([A-Za-z0-9]+):\s*(.*)$",
    r"^(\w+)\s*-\s*(.*)$",
    r".*",
    r"^(Speaker \d+):(.*)$",
    r"(cat|dog)+",  # disjoint alternation under a repeat is fine
    r"((a)(b))+",  # nested groups without nested repeats are fine
]


@pytest.mark.parametrize("pattern", CATASTROPHIC_PATTERNS)
def test_rejects_catastrophic_patterns(pattern):
    with pytest.raises(UnsafePatternError):
        assert_safe_pattern(pattern)


@pytest.mark.parametrize("pattern", LEGITIMATE_PATTERNS)
def test_accepts_legitimate_patterns(pattern):
    assert_safe_pattern(pattern)  # must not raise


def test_rejects_overlong_pattern():
    with pytest.raises(UnsafePatternError):
        assert_safe_pattern("a" * (MAX_PATTERN_LENGTH + 1))


def test_rejects_invalid_regex_syntax():
    with pytest.raises(UnsafePatternError):
        assert_safe_pattern("(unclosed")
