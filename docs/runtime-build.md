# The embedded-runtime build

`scripts/runtime/`, `.github/workflows/release-workflow.yml` (`runtime` job)

A second release format next to the PyInstaller build. Instead of freezing everything into
one binary, a [PyApp](https://github.com/ofek/pyapp) launcher embeds a small, real Python
installation with only the base dependencies. Transcription, normalisation and recording
are **components**: downloaded later, from PyPI, pinned by hash to exactly what this build
was tested with.

| | PyInstaller build | Embedded runtime |
| - | ----------------- | ---------------- |
| Linux binary | ~164 MB, everything bundled | ~59 MB, components downloaded later |
| Startup | unpacks ~447 MB to a temp dir on every launch | unpacks once (~1.4 s), then ~0.05 s |
| Adding a feature later | impossible - no pip, no environment | `components install <name>` |
| Offline | yes | yes, for everything already installed |

Release assets: `Chronicler-modular` on Linux; on Windows `Chronicler-modular.exe` for the
desktop and `Chronicler-modular-cli.exe` for `server` and the `components` commands.

## Why not load packages into the PyInstaller build

That was considered and rejected. A frozen app only contains the standard-library modules
its analysis found, its own bundled modules shadow anything added later, and a package
built against a different interpreter fails in ways that only show on a user's machine.
PyInstaller's maintainers advise against it for exactly these reasons. A standalone
CPython is a normal interpreter, so none of that applies.

## What goes into the binary

`scripts/runtime/build.py`, in order:

1. The [python-build-standalone](https://github.com/astral-sh/python-build-standalone)
   CPython for the platform, `install_only_stripped`.
2. The base dependencies from `scripts/runtime/locks/<platform>/base.lock`, installed with
   `--require-hashes --no-deps --only-binary :all:`. No resolver runs and no build script
   executes.
3. The Chronicler wheel.
4. The Flet desktop client, so the first launch never downloads one. On Linux it is the
   `debian10` client, the lowest glibc Flet builds for, matching the `manylinux_2_28`
   wheels. `desktop.main.packaged_flet_client()` finds it under `sys.prefix/share`.
5. The component locks, under `share/chronicler/locks` - which is also how
   `extras.is_embedded_runtime()` recognises this build.
6. `scripts/runtime/launcher.py`, installed as the `chronicler_launcher` entry point.

Then it is trimmed (Tcl/Tk, IDLE, headers, and on Linux `libpython.so`, a duplicate of the
statically linked interpreter), archived as `tar.zst` at level 19 and compiled into the
launcher with `cargo`. Every download is pinned by URL and sha256 in
`scripts/runtime/pins.py`; a mismatch stops the build.

PyApp runs with `PYAPP_FULL_ISOLATION` and `PYAPP_SKIP_INSTALL`: the embedded runtime is
unpacked as-is and nothing is installed on first launch, which is what makes it work
offline.

## Locks

`scripts/runtime/locks.py` resolves everything together first, so a package shared by the
base and a component - or two components - gets one version everywhere. The base is then
locked against those versions, and each component lock holds only what the base does not
already provide.

```bash
python scripts/runtime/locks.py            # after a pyproject.toml change; keeps existing pins
python scripts/runtime/locks.py --upgrade  # move everything to the newest allowed versions
```

The CI job *Runtime Locks Are Current* runs `--check` and fails when the committed locks no
longer match `pyproject.toml`. uv resolves for Windows from Linux, so one runner checks both.

`llama-cpp-python` is not a component and never will be here: PyPI has no wheels for it, so
a hash-pinned, binary-only install is impossible. Local `.gguf` models stay a source-install
feature; an OpenAI-compatible server such as Ollama needs nothing.

## Components

Until the component manager is part of the app, installing is a command line:

```bash
./Chronicler-modular components install transcription normalization recording
./Chronicler-modular components where
```

The set of requested components is installed with pip `--target` into a staging directory
named after a hash of their locks, and only renamed into place when pip succeeded - so a
failed or interrupted install never leaves a half-populated directory behind. An `active`
pointer names the set in use, and the launcher appends it to `sys.path` before Chronicler
starts. Appending, not prepending: the runtime's own packages always win.

Because the directory is keyed by the locks rather than the app version, an update whose
locks did not change reuses what is already installed.

Inside this build `extras.can_install()` is False and `missing_message()` names the
component command instead of pip: pip would work, but whatever it installed into the
runtime would be gone after the next update.

## Windows: two launchers

With `PYAPP_IS_GUI` PyApp starts `pythonw.exe` and exits immediately. That is right for a
double-clicked desktop app and wrong for anything whose output matters, so Windows gets
both variants. They are built from the same runtime archive and share one unpacked
installation.

PyApp's launcher is a console-subsystem executable even in its GUI mode, so a double-click
still opened a console window next to the app (CI reads the PE header to report this).
`build.py` therefore prepends `#![windows_subsystem = "windows"]` to PyApp's `main.rs` for
the GUI variant - the source is built here anyway, so a one-line patch beats a fork.

Linux needs only the console variant: there is no console window to hide, and the GUI mode
would detach `chronicler server` from the terminal that started it.

## Known rough edges

* **The first launch on Windows unpacks for a while.** Measured for the same ~8,000 files: about
  1 s on Linux, 8-9 s on a CI runner with Defender real-time protection off, and about 20 s
  on a desktop with it on. Later launches take under a second. The GUI launcher shows
  nothing while it unpacks, so an impatient second double-click is likely. Fewer files (the
  standard library as a zip) or a first-run notice would help.
* **Windows asks before running an unsigned executable**, exactly as it does for the
  PyInstaller build.
* **The first Whisper model download can stall on Windows**, leaving an incomplete cached
  snapshot that fails the transcription; restarting the app and transcribing again works.
  Not yet reproduced or explained.

## Where it lives on disk

PyApp unpacks into `~/.local/share/pyapp/chronicler/<id>/<version>` on Linux and the
equivalent under `%LOCALAPPDATA%` on Windows. The directory is keyed by version, not
content, so two local builds with the same `__version__` reuse whichever was unpacked
first - delete it, or bump the version, when testing a rebuild. Components live under the
platform's user data directory, in `Chronicler/components`.

Old versions are not yet removed after an update.

## Building locally

```bash
uv run --no-project --python 3.12 --with zstandard python scripts/runtime/build.py
uv run --no-project --python 3.12 python scripts/runtime/smoke.py dist/runtime/Chronicler-console
```

Needs `uv` and `cargo` on PATH, and has to run on the platform it builds for.
`smoke.py` launches the binary, checks it found its Flet client, installs every component
and transcribes a pinned 16-second sample with the tiny Whisper model. The release
workflow runs the same script before attaching anything.

## Testing

`tests/scripts/runtime/` covers lock parsing and rendering, the staleness check, the
committed locks themselves (every requirement hashed, no component repeating the base, the
locked `flet-desktop` matching the shipped client, no `llama-cpp-python`), the pins, and
the PE subsystem reader. `tests/chronicler/core/test_extras.py` and
`tests/chronicler/desktop/test_main.py` cover the embedded-runtime behaviour in the app.
