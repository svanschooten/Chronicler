"""Building SQL `LIKE` patterns and FTS5 queries from user-typed search text."""

import re

LIKE_ESCAPE = "!"


def contains_pattern(query: str) -> str:
    """A `LIKE` pattern matching any value containing `query` as a literal substring."""
    escaped = (
        query.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", f"{LIKE_ESCAPE}%")
        .replace("_", f"{LIKE_ESCAPE}_")
    )
    return f"%{escaped}%"


def fts_query(query: str) -> str | None:
    """
    An FTS5 MATCH expression finding lines that contain every word of `query`, the last one
    as a prefix so results appear while it is still being typed. None when `query` has no
    words. Each word is quoted, so nothing typed is read as FTS5 syntax (AND, NEAR, column
    filters, unbalanced quotes).
    """
    words = re.findall(r"\w+", query)
    if not words:
        return None
    terms = [f'"{word}"' for word in words]
    terms[-1] += "*"
    return " ".join(terms)
