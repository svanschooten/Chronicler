"""User-supplied regex patterns: a length cap, and a time bound on every match."""

import regex

MAX_PATTERN_LENGTH = 500
MATCH_TIMEOUT_SECONDS = 5.0


class UnsafePatternError(ValueError):
    pass


class PatternTimeoutError(RuntimeError):
    pass


def compile_pattern(pattern: str, flags: int = 0) -> "regex.Pattern[str]":
    """
    Compile a user-supplied pattern, rejecting one that is too long or not valid.

    Match with `run_timed` so one pattern can neither hold the GIL nor run forever.
    """
    if len(pattern) > MAX_PATTERN_LENGTH:
        raise UnsafePatternError(
            f"Pattern exceeds maximum length of {MAX_PATTERN_LENGTH} characters"
        )
    try:
        return regex.compile(pattern, flags)
    except regex.error as error:
        raise UnsafePatternError(f"Invalid regular expression: {error}") from error


def assert_safe_pattern(pattern: str) -> None:
    compile_pattern(pattern)


def run_timed(pattern: "regex.Pattern[str]", method, *args):
    """
    Call `method` (a bound match, fullmatch, sub... of `pattern`) with a time limit.

    `concurrent=True` releases the GIL while matching, so a slow pattern in a worker
    thread does not stall the event loop.
    """
    try:
        return method(*args, timeout=MATCH_TIMEOUT_SECONDS, concurrent=True)
    except TimeoutError as error:
        raise PatternTimeoutError(
            f"Pattern {pattern.pattern!r} took longer than {MATCH_TIMEOUT_SECONDS:g} seconds "
            "on one line. Simplify the pattern."
        ) from error
