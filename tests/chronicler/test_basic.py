import re

import tomllib

from chronicler import __version__
from tests.paths import REPO_ROOT


def test_version_is_a_release_number():
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__), __version__


def test_the_version_is_written_in_exactly_one_place():
    """
    Cutting a release used to mean editing the same number in four files and hoping none
    was missed. Hatchling now reads it out of `chronicler/__init__.py`, so a bump is that
    one line - this fails if a literal creeps back into pyproject.toml alongside it.
    """
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())

    assert "version" not in pyproject["project"], "pyproject must not carry its own literal"
    assert pyproject["project"]["dynamic"] == ["version"]
    assert pyproject["tool"]["hatch"]["version"]["path"] == "chronicler/__init__.py"
