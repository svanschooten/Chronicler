"""Every skip for a missing extra goes through `tests.extras.require_extra`."""

import re
import sys
from pathlib import Path

import pytest

from chronicler.core.extras import get_extra
from tests.extras import require_extra, skip_reason

TESTS = Path(__file__).resolve().parent
# The wording the CI job greps for, as its workflow step spells it.
CI_PATTERN = re.compile(r"requires the '[a-z]+' extra")


def test_no_test_module_skips_for_an_import_on_its_own():
    offenders = [
        str(path.relative_to(TESTS))
        for path in TESTS.rglob("*.py")
        if path.name not in ("extras.py", "test_extras_skips.py")
        and "importorskip(" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], "use tests.extras.require_extra so CI sees the skip"


def test_the_reason_is_the_one_ci_looks_for():
    assert CI_PATTERN.fullmatch(skip_reason("normalization"))


def test_require_extra_skips_when_a_module_of_the_extra_is_missing(monkeypatch):
    # None in sys.modules makes importing that name raise ImportError.
    monkeypatch.setitem(sys.modules, get_extra("normalization").modules[-1], None)

    with pytest.raises(pytest.skip.Exception, match=skip_reason("normalization")):
        require_extra("normalization")
