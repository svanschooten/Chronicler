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
