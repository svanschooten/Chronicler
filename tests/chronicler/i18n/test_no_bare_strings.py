"""
The guard that keeps the interface translated.

Half the views were hardcoded English while the catalogue already held their keys, and
nothing failed: the catalogue tests only check that keys which *are* used exist, not that
strings reach the user through `t()` at all. This fails on a bare literal instead.
"""

import ast
import pathlib

import pytest

DESKTOP = pathlib.Path("chronicler/desktop")

USER_FACING_KEYWORDS = {"label", "hint_text", "tooltip", "helper_text", "error_text", "error"}
USER_FACING_CALLS = {"Text", "SnackBar"}

ALLOWED = {
    "",
    " ",
    "·",
    " · ",
    "monospace",
    "Imported",
}


def _is_translated(node: ast.expr) -> bool:
    """A `t(...)` call, an f-string, or anything that is not a bare literal."""
    if isinstance(node, ast.Constant):
        return not isinstance(node.value, str) or node.value in ALLOWED
    if isinstance(node, ast.Call):
        target = node.func
        name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
        return name != "Text" or _is_translated(node.args[0]) if node.args else True
    return True


def _offences(path: pathlib.Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text())):
        if not isinstance(node, ast.Call):
            continue

        callee = node.func
        name = callee.attr if isinstance(callee, ast.Attribute) else getattr(callee, "id", "")
        if (
            name in USER_FACING_CALLS
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and not _is_translated(node.args[0])
        ):
            found.append(f"{path}:{node.lineno} ft.{name}({node.args[0].value!r})")

        for keyword in node.keywords:
            if (
                keyword.arg in USER_FACING_KEYWORDS
                and isinstance(keyword.value, ast.Constant)
                and not _is_translated(keyword.value)
            ):
                found.append(f"{path}:{keyword.value.lineno} {keyword.arg}={keyword.value.value!r}")
    return found


def _desktop_modules() -> list[pathlib.Path]:
    return sorted(p for p in DESKTOP.rglob("*.py") if p.name != "__init__.py")


def test_there_are_desktop_modules_to_check():
    """A guard on the guard: a bad glob would make every case below pass vacuously."""
    assert len(_desktop_modules()) > 15


@pytest.mark.parametrize("path", _desktop_modules(), ids=lambda p: str(p))
def test_no_user_facing_string_is_hardcoded(path):
    offences = _offences(path)

    assert not offences, "Wrap these in t(...) and add the key to every catalogue:\n" + "\n".join(
        offences
    )
