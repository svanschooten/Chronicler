#!/usr/bin/env bash
#
# Regenerates Chronicler.spec, which is what the release workflow actually builds. Run this
# after a Flet upgrade changes what `flet pack` emits, then diff the spec before committing.
#
# `flet pack` passes --noconsole unless --debug-console is given, so the windowed build the
# app depends on comes out of here by default. See docs/packaging.md.

set -euo pipefail

flet pack chronicler/__main__.py \
            --name Chronicler \
            --icon assets/icon.png \
            --add-data "assets:assets" \
            --add-data "chronicler/migrations:chronicler/migrations" \
            --add-data "chronicler/webclient/src:chronicler/webclient/src" \
            --hidden-import aiosqlite \
            --hidden-import re._parser \
            --hidden-import logging.config

python3 - <<'PY'
"""
Puts the explanatory comments back into the freshly generated spec, and fails if `flet pack`
stopped emitting a windowed build. A regen used to drop both silently.
"""

from pathlib import Path

MARKER = "# -*- mode: python ; coding: utf-8 -*-\n"

HEADER = """#
# Regenerate with scripts/pack.sh, which runs `flet pack` with the data files and hidden
# imports below. Anything hand-edited here must be mirrored into that script, or the next
# regen silently drops it. See docs/packaging.md.
"""

CONSOLE = """    # Windowed, which is what `flet pack` emits unless --debug-console is passed. Setup
    # therefore happens in the Flet window (chronicler/desktop/views/wizard.py) rather than
    # on stdin, and `chronicler server` borrows the calling terminal's console at startup -
    # see attach_windows_console() in chronicler/__main__.py and docs/packaging.md.
"""

spec = Path("Chronicler.spec")
text = spec.read_text()

if "    console=False,\n" not in text:
    raise SystemExit("flet pack emitted a console build; the app expects a windowed one")

text = text.replace(MARKER, MARKER + HEADER, 1)
text = text.replace("    console=False,\n", CONSOLE + "    console=False,\n", 1)
spec.write_text(text)
PY

echo "Chronicler.spec regenerated - diff it before committing."
