"""Repo-relative paths for tests that read fixture files off disk.

Anchored here rather than with `Path(__file__).parents[n]` in each test module: the
tests tree mirrors the package tree, so a module's depth changes whenever it moves,
and a hardcoded parent count silently starts pointing at the wrong directory.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"
