"""
Skipping tests that need an optional extra, in the one wording CI looks for.

The *Tests With Every Extra* CI job installs every runtime lock and fails if a test is
skipped with "requires the '<extra>' extra". A skip worded any other way would pass that
job silently, so every such skip goes through `require_extra`, and
`tests/test_extras_skips.py` fails on an `importorskip` anywhere else. See docs/testing.md.
"""

import pytest

from chronicler.core.extras import get_extra


def skip_reason(extra: str) -> str:
    return f"requires the '{extra}' extra"


def require_extra(extra: str) -> None:
    """
    Skips the calling test module unless every module the extra provides imports.

    `exc_type=ImportError` makes the skip mean "cannot be imported" rather than "is absent",
    the same distinction `extras.is_available()` draws.
    """
    for module in get_extra(extra).modules:
        pytest.importorskip(module, reason=skip_reason(extra), exc_type=ImportError)
