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

USER_FACING_KEYWORDS = {
    "label",
    "hint_text",
    "tooltip",
    "helper_text",
    "error_text",
    "error",
    "dialog_title",
}
USER_FACING_CALLS = {
    "Text",
    "SnackBar",
    "show_snackbar",
    "TextButton",
    "FilledButton",
    "ElevatedButton",
    "Choice",
}
USER_FACING_PARAMETERS = {"confirm_label", "dialog_title", "title", "message", "label", "purpose"}

ALLOWED = {
    "",
    " ",
    "·",
    " · ",
    "monospace",
    "Imported",
}


def _has_words(node: ast.expr) -> bool:
    """
    A bare string, or an f-string whose fixed text holds a word. `f"{n}%"` has none, and
    neither has `f"v{version}"`, whose one letter is a unit rather than a sentence.
    """
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str) and node.value not in ALLOWED
    if isinstance(node, ast.JoinedStr):
        return any(
            isinstance(part, ast.Constant)
            and isinstance(part.value, str)
            and sum(c.isalpha() for c in part.value) >= 2
            for part in node.values
        )
    return False


def _default_offences(
    path: pathlib.Path, node: ast.FunctionDef | ast.AsyncFunctionDef
) -> list[str]:
    """A default for a parameter that ends up on screen is a string that skips `t()`."""
    args = node.args
    positional = args.posonlyargs + args.args
    pairs = list(zip(reversed(positional), reversed(args.defaults), strict=False))
    pairs += [(a, d) for a, d in zip(args.kwonlyargs, args.kw_defaults, strict=True) if d]
    return [
        f"{path}:{default.lineno} {arg.arg}={getattr(default, 'value', '')!r} (default)"
        for arg, default in pairs
        if arg.arg in USER_FACING_PARAMETERS and _has_words(default)
    ]


def _offences(path: pathlib.Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            found.extend(_default_offences(path, node))
            continue
        if not isinstance(node, ast.Call):
            continue

        callee = node.func
        name = callee.attr if isinstance(callee, ast.Attribute) else getattr(callee, "id", "")
        if name in USER_FACING_CALLS and node.args and _has_words(node.args[0]):
            found.append(f"{path}:{node.lineno} {name}({ast.unparse(node.args[0])})")

        for keyword in node.keywords:
            if keyword.arg in USER_FACING_KEYWORDS and _has_words(keyword.value):
                found.append(
                    f"{path}:{keyword.value.lineno} {keyword.arg}={ast.unparse(keyword.value)}"
                )
    return found


RETURNS_MESSAGES = {"imports.py"}
"""Modules whose `return "..."` strings are shown to the user as they are."""


def _returned_text(path: pathlib.Path) -> list[str]:
    if path.name not in RETURNS_MESSAGES:
        return []
    return [
        f"{path}:{node.lineno} return {ast.unparse(node.value)}"
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Return) and node.value is not None and _has_words(node.value)
    ]


def _desktop_modules() -> list[pathlib.Path]:
    return sorted(p for p in DESKTOP.rglob("*.py") if p.name != "__init__.py")


def test_there_are_desktop_modules_to_check():
    """A guard on the guard: a bad glob would make every case below pass vacuously."""
    assert len(_desktop_modules()) > 15


@pytest.mark.parametrize("path", _desktop_modules(), ids=lambda p: str(p))
def test_no_user_facing_string_is_hardcoded(path):
    offences = _offences(path) + _returned_text(path)

    assert not offences, "Wrap these in t(...) and add the key to every catalogue:\n" + "\n".join(
        offences
    )
