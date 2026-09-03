"""Building SQL `LIKE` patterns from user-typed search text."""

LIKE_ESCAPE = "!"


def contains_pattern(query: str) -> str:
    """A `LIKE` pattern matching any value containing `query` as a literal substring."""
    escaped = (
        query.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", f"{LIKE_ESCAPE}%")
        .replace("_", f"{LIKE_ESCAPE}_")
    )
    return f"%{escaped}%"
