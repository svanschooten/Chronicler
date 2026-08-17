"""Tests for LIKE pattern construction."""

from chronicler.core.sqlite.patterns import LIKE_ESCAPE, contains_pattern


def test_plain_text_becomes_a_contains_pattern():
    assert contains_pattern("emberfall") == "%emberfall%"


def test_percent_is_escaped_rather_than_matching_everything():
    """A bare "%" used to match every row, which reads as the search box being broken."""
    assert contains_pattern("100%") == f"%100{LIKE_ESCAPE}%%"


def test_underscore_is_escaped_rather_than_matching_any_character():
    assert contains_pattern("a_b") == f"%a{LIKE_ESCAPE}_b%"


def test_the_escape_character_itself_is_escaped_first():
    """Otherwise escaping "%" would produce a sequence the user's own "!" could hijack."""
    assert contains_pattern(LIKE_ESCAPE) == f"%{LIKE_ESCAPE}{LIKE_ESCAPE}%"
    assert contains_pattern(f"{LIKE_ESCAPE}%") == f"%{LIKE_ESCAPE}{LIKE_ESCAPE}{LIKE_ESCAPE}%%"


def test_empty_query_matches_anything():
    assert contains_pattern("") == "%%"
