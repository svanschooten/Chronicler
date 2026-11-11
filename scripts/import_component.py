#!/usr/bin/env python
"""
Imports one runtime component's modules, as `chronicler.core.extras` lists them, so CI can
show a component's lock is complete on its own. See docs/runtime-build.md.

    python scripts/import_component.py recording
"""

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chronicler.core.extras import get_extra  # noqa: E402


def main(component: str) -> None:
    for module in get_extra(component).modules:
        try:
            importlib.import_module(module)
        except Exception as error:
            # sounddevice loads PortAudio, then initialises it, which needs an audio
            # server a CI runner does not have. Reaching that error means the library
            # was found, so nothing the lock should provide is missing. A missing
            # library is an OSError, and still fails.
            if type(error).__name__ != "PortAudioError":
                raise
            print(f"imported {module} (PortAudio found no audio server: {error})")
            continue
        print(f"imported {module}")


if __name__ == "__main__":
    main(sys.argv[1])
