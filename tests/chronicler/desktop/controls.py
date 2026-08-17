"""Helpers for asserting against a built Flet control tree.

Views here are unit-tested by building them and inspecting the controls they
produced, rather than by rendering - so several test modules need the same walk over
a tree whose children hang off `controls`, `items` or `content` depending on the
control.
"""

from collections.abc import Callable

import flet as ft


def find_controls(root, predicate: Callable[[object], bool]) -> list:
    """Depth-first walk of a Flet control tree, collecting nodes matching `predicate`."""
    found: list = []
    if predicate(root):
        found.append(root)
    for attr in ("controls", "items"):
        for child in getattr(root, attr, None) or []:
            found.extend(find_controls(child, predicate))
    content = getattr(root, "content", None)
    if content is not None:
        found.extend(find_controls(content, predicate))
    return found


def text_values(root) -> list[str]:
    """Every ft.Text value in the tree, for asserting what a view actually displays."""
    roots = root.controls if isinstance(root, ft.Column) else [root]
    values: list[str] = []
    for node in roots:
        values.extend(c.value for c in find_controls(node, lambda c: isinstance(c, ft.Text)))
    return values
