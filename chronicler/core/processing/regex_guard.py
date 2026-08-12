"""Static rejection of regex patterns shaped for catastrophic backtracking (ReDoS).

Import regexes arrive from RPC callers (TaskService.queue_import) and get compiled and
matched against attacker-influenced content (uploaded file lines). RegexImporter matches
line-by-line rather than against the whole file, so the realistic attack is a crafted
pattern matched against a long adversarial line, which can blow up matching time
exponentially in CPython's backtracking engine. Two shapes cause this in practice:

  1. A quantified group whose own body is itself quantified, e.g. `(a+)+`.
  2. A quantified group containing alternation whose branches can match overlapping
     content, e.g. `(a|a)*` or `(a|aa)+` - the engine can attribute the same matched
     text to different combinations of branch choices.

This is a static, zero-cost pre-filter for both shapes. It is not a CPU-time bound -
Python threads can't be force-killed and CPython's regex matcher doesn't release the
GIL during backtracking, so a true hard bound needs a subprocess-based watchdog. That's
deliberately deferred: it overlaps with the worker-loop rework already planned for
atomic task claiming and retries, and building a regex-specific timeout now would just
be redone there. See TODO.md, Phase 3.
"""

import re
from re import _parser as sre_parser  # type: ignore[attr-defined]

MAX_PATTERN_LENGTH = 500

# sre_parser op names for a repeat node: MAX_REPEAT covers `*`/`+`/`{m,n}`, MIN_REPEAT
# covers the non-greedy forms `*?`/`+?`/`{m,n}?`.
_REPEAT_OPS = {"MAX_REPEAT", "MIN_REPEAT"}
# How wide a character RANGE we'll enumerate when comparing branches for overlap.
_MAX_RANGE_SPAN = 64


class UnsafePatternError(ValueError):
    pass


def _op_name(op) -> str:
    return getattr(op, "name", str(op))


def _leading_chars(subpattern) -> set[int] | None:
    """Best-effort set of literal codepoints `subpattern` could start matching with.
    Returns None when it can't be determined confidently - treated conservatively
    (as "might overlap with anything") by callers.
    """
    if not subpattern.data:
        return None  # empty alternative - can't rule out overlap with anything
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
                return None  # CATEGORY/NEGATE/etc - don't try to be precise
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
    """True if `subpattern` (the body of some enclosing repeat) contains, anywhere
    within it, another repeat or an alternation with overlapping branches - both let
    the backtracking engine explore exponentially many equivalent ways to match the
    same input.
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
    """Raise UnsafePatternError if `pattern` is too long or structurally shaped for
    catastrophic backtracking. Does not guarantee every ReDoS pattern is caught (see
    module docstring) - it closes the realistic, textbook attack surface at zero
    runtime cost.
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
