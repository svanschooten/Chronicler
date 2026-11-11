"""
User-supplied regex patterns: a length cap, a time bound on every match, and one on all
the matches a whole import or clean makes.
"""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

import regex

MAX_PATTERN_LENGTH = 500
MATCH_TIMEOUT_SECONDS = 5.0
TOTAL_TIMEOUT_SECONDS = 60.0

# When the enclosing `time_limit` ends, and how long it allowed, for the message.
_deadline: ContextVar[tuple[float, float] | None] = ContextVar("regex_deadline", default=None)


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


@contextmanager
def time_limit(seconds: float | None = None) -> Iterator[None]:
    """
    Bounds every `run_timed` call inside the block together, at `TOTAL_TIMEOUT_SECONDS`
    unless given. Without it a pattern just under the per-match limit on every line of a
    long transcript would hold the worker for hours. A nested block keeps the earlier
    deadline.
    """
    limit = TOTAL_TIMEOUT_SECONDS if seconds is None else seconds
    bound = (time.monotonic() + limit, limit)
    outer = _deadline.get()
    if outer is not None and outer[0] < bound[0]:
        bound = outer
    token = _deadline.set(bound)
    try:
        yield
    finally:
        _deadline.reset(token)


def run_timed(pattern: "regex.Pattern[str]", method, *args):
    """
    Call `method` (a bound match, fullmatch, sub... of `pattern`) with a time limit: the
    per-match one, or what is left of the enclosing `time_limit`, whichever ends first.

    `concurrent=True` releases the GIL while matching, so a slow pattern in a worker
    thread does not stall the event loop.
    """
    timeout = MATCH_TIMEOUT_SECONDS
    bound = _deadline.get()
    total_bound = False
    if bound is not None:
        deadline, limit = bound
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _too_slow_overall(pattern, limit)
        if remaining < timeout:
            timeout, total_bound = remaining, True
    try:
        return method(*args, timeout=timeout, concurrent=True)
    except TimeoutError as error:
        if bound is not None and total_bound:
            raise _too_slow_overall(pattern, bound[1]) from error
        raise PatternTimeoutError(
            f"Pattern {pattern.pattern!r} took longer than {MATCH_TIMEOUT_SECONDS:g} seconds "
            "on one line. Simplify the pattern."
        ) from error


def _too_slow_overall(pattern: "regex.Pattern[str]", limit: float) -> PatternTimeoutError:
    """`limit` is what the enclosing `time_limit` allowed, which callers may set."""
    return PatternTimeoutError(
        f"Pattern {pattern.pattern!r} took longer than {limit:g} seconds "
        "over the whole transcript. Simplify the pattern."
    )
