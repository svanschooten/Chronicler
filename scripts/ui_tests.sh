#!/usr/bin/env bash
# Runs the rendered UI tests in tests/ui/ on a virtual display. Linux only.
#
# Needs Flutter on PATH (the version `python scripts/ui_host.py --flutter-version` names)
# and, from apt: clang ninja-build libgtk-3-dev xvfb, plus ffmpeg for screens of failures.
# Installs Flet's test extras into the active environment if they are missing, and
# prepares the Flutter client in build/ui-host the first time, or after a Flet upgrade.
#
# Usage: scripts/ui_tests.sh [pytest arguments]
# See docs/testing.md.

set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON=${PYTHON:-python}
HOST_DIR=build/ui-host

for tool in flutter xvfb-run; do
    if ! command -v "$tool" >/dev/null; then
        echo "error: $tool is not on PATH; see docs/testing.md" >&2
        exit 1
    fi
done

flet_version=$("$PYTHON" -c 'from importlib.metadata import version; print(version("flet"))')
wanted_flutter=$("$PYTHON" scripts/ui_host.py --flutter-version)
found_flutter=$(flutter --version --machine 2>/dev/null \
    | "$PYTHON" -c 'import json, sys; print(json.load(sys.stdin)["frameworkVersion"])')
if [ "$wanted_flutter" != "$found_flutter" ]; then
    echo "warning: Flet $flet_version builds with Flutter $wanted_flutter," \
        "but Flutter $found_flutter is on PATH" >&2
fi

# flet.testing imports numpy, Pillow and scikit-image, which nothing else needs.
if ! "$PYTHON" -c 'import numpy, PIL, skimage' 2>/dev/null; then
    echo "Installing flet[test]==$flet_version"
    "$PYTHON" -m pip install --quiet "flet[test]==$flet_version"
fi

if [ "$(cat "$HOST_DIR/flet-version" 2>/dev/null)" != "$flet_version" ]; then
    echo "Preparing the Flutter client for Flet $flet_version in $HOST_DIR"
    "$PYTHON" scripts/ui_host.py "$HOST_DIR" >/dev/null
    echo "$flet_version" >"$HOST_DIR/flet-version"
fi

# Without the X11 backend and software GL the client draws nothing on Xvfb. WSLg sets
# WAYLAND_DISPLAY, which would pull GTK onto Wayland instead.
exec env -u WAYLAND_DISPLAY \
    GDK_BACKEND=x11 \
    LIBGL_ALWAYS_SOFTWARE=1 \
    FLET_TEST_FLUTTER_APP_DIR="$PWD/$HOST_DIR/client" \
    CHRONICLER_UI_SCREENSHOTS="${CHRONICLER_UI_SCREENSHOTS:-$PWD/build/ui-screenshots}" \
    xvfb-run -a -s "-screen 0 1600x1000x24" \
    "$PYTHON" -m pytest tests/ui "$@"
