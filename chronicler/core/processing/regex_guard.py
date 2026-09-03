"""Static rejection of regex patterns shaped for catastrophic backtracking (ReDoS)."""

import re
from re import _parser as sre_parser  # type: ignore[attr-defined]

MAX_PATTERN_LENGTH = 500

_REPEAT_OPS = {"MAX_REPEAT", "MIN_REPEAT"}
_MAX_RANGE_SPAN = 64


class UnsafePatternError(ValueError):
    pass


def _op_name(op) -> str:
    return getattr(op, "name", str(op))


def _leading_chars(subpattern) -> set[int] | None:
    """Best-effort set of literal codepoints `subpattern` could start matching with."""
    if not subpattern.data:
        return None
    op, av = subpattern.data[0]
    name = _op_name(op)
    if name == "LITERAL":
        return {av}
    if name == "IN":
        chars: set[int] = set()
        for item_op, item_av in av:
            item_name = _op_name(item_op)
            if item_name == "LITERAL":
                chars.add(item_av)
            elif item_name == "RANGE":
                lo, hi = item_av
                if hi - lo > _MAX_RANGE_SPAN:
                    return None
                chars.update(range(lo, hi + 1))
            else:
                return None
        return chars
    if name == "SUBPATTERN":
        _group, _add_flags, _del_flags, body = av
        return _leading_chars(body)
    return None


def _branches_overlap(branches) -> bool:
    leading_sets = [_leading_chars(b) for b in branches]
    for i in range(len(leading_sets)):
        for j in range(i + 1, len(leading_sets)):
            a, b = leading_sets[i], leading_sets[j]
            if a is None or b is None or (a & b):
                return True
    return False


def _is_dangerous_body(subpattern) -> bool:
    """
    True if `subpattern` (the body of some enclosing repeat) contains, anywhere within it,
    another repeat or an alternation with overlapping branches - both let the backtracking
    engine explore exponentially many equivalent ways to match the same input.
    """
    for op, av in subpattern.data:
        name = _op_name(op)
        if name in _REPEAT_OPS:
            return True
        if name == "BRANCH":
            _, branches = av
            if _branches_overlap(branches):
                return True
            if any(_is_dangerous_body(branch) for branch in branches):
                return True
        elif name == "SUBPATTERN":
            _group, _add_flags, _del_flags, body = av
            if _is_dangerous_body(body):
                return True
        elif name in ("ASSERT", "ASSERT_NOT"):
            _direction, body = av
            if _is_dangerous_body(body):
                return True
    return False


def _find_unsafe_repeat(subpattern) -> bool:
    """Walk the whole parsed pattern for a repeat node whose body is dangerous."""
    for op, av in subpattern.data:
        name = _op_name(op)
        if name in _REPEAT_OPS:
            _min, _max, body = av
            if _is_dangerous_body(body) or _find_unsafe_repeat(body):
                return True
        elif name == "SUBPATTERN":
            _group, _add_flags, _del_flags, body = av
            if _find_unsafe_repeat(body):
                return True
        elif name == "BRANCH":
            _, branches = av
            if any(_find_unsafe_repeat(branch) for branch in branches):
                return True
        elif name in ("ASSERT", "ASSERT_NOT"):
            _direction, body = av
            if _find_unsafe_repeat(body):
                return True
    return False


def assert_safe_pattern(pattern: str) -> None:
    """
    Raise UnsafePatternError if `pattern` is too long or structurally shaped for
    catastrophic backtracking.
    """
    if len(pattern) > MAX_PATTERN_LENGTH:
        raise UnsafePatternError(
            f"Pattern exceeds maximum length of {MAX_PATTERN_LENGTH} characters"
        )

    try:
        parsed = sre_parser.parse(pattern)
    except re.error as e:
        raise UnsafePatternError(f"Invalid regular expression: {e}") from e

    if _find_unsafe_repeat(parsed):
        raise UnsafePatternError(
            "Pattern contains a nested or ambiguous repeat (e.g. (a+)+ or (a|a)*), "
            "which can cause catastrophic backtracking"
        )
