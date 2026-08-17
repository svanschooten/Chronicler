"""Building SQL `LIKE` patterns from user-typed search text."""

#: Chosen over the more usual backslash because SQLite has no default LIKE escape
#: character at all - one has to be declared per query via `ESCAPE`, and SQLAlchemy's
#: `escape=` parameter does that for us. `!` is rare in transcript titles and tags, so
#: it shows up less often in the escaped output than a backslash would.
LIKE_ESCAPE = "!"


def contains_pattern(query: str) -> str:
    """A `LIKE` pattern matching any value containing `query` as a literal substring.

    The wildcards in the user's own text are escaped: someone searching for "100%" means
    a chronicle whose title contains "100%", not "anything containing 100". Without this,
    a bare `%` matched every row and `_` matched any single character, which reads as the
    search box being broken rather than as a feature.

    Pair with `escape=LIKE_ESCAPE` on the `ilike()` call.
    """
    escaped = (
        query.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", f"{LIKE_ESCAPE}%")
        .replace("_", f"{LIKE_ESCAPE}_")
    )
    return f"%{escaped}%"
