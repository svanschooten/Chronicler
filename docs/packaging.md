# Packaging

`Chronicler.spec`, `scripts/pack.sh`, `.github/workflows/release-workflow.yml`

Standalone builds for Linux and Windows come out of PyInstaller. The release workflow
runs `pyinstaller Chronicler.spec` on `ubuntu-latest` and `windows-latest` and attaches
both binaries to the release.

## The spec is the source of truth, the script regenerates it

`scripts/pack.sh` runs `flet pack` with the data files and hidden imports the app needs.
It writes `Chronicler.spec`, which is what actually gets built — so the script exists to
recreate the spec after a Flet upgrade changes what `flet pack` emits, not as the build
step itself.

Anything hand-edited into the spec has to be mirrored into the script, or the next regen
silently drops it. Today that is one setting: `console`.

## Why the build is windowed

`console=False`. Double-clicking the app must not flash up a terminal behind the window.

The cost is that a GUI-subsystem executable on Windows gets no console *at all* — not
even the one it was launched from. `sys.stdin`, `sys.stdout` and `sys.stderr` are dead
ends, so anything that prints or reads goes nowhere. Two things follow.

### Desktop setup happens on screen

The console wizard in `core/wizard.py` is `input()` all the way down. It cannot serve a
packaged desktop launch, and not only on Windows: a Linux binary started from a file
manager has no controlling terminal either, so `input()` raises `EOFError` there too.

Desktop mode therefore uses `desktop/views/wizard.py`, which asks the same questions as
Flet controls inside the window that is already open. `__main__.main()` routes to it by
not calling `run_wizard` for `client:desktop` at all; `desktop.main.start()` decides,
using the same `Settings.validate_for_mode` gate the other modes use.

The Flet wizard deliberately covers **only** the two modes a desktop window can run in —
full stack and thin client. Server and web client are started from a terminal, which is
exactly where the console wizard works, so they keep it and the desktop wizard does not
duplicate them.

### `chronicler server` borrows the calling terminal

`attach_windows_console()` in `__main__.py` calls `AttachConsole(ATTACH_PARENT_PROCESS)`
before argparse runs. When the executable was started from a terminal, that hands the
process its parent's console and the three standard streams are reopened on `CONIN$` /
`CONOUT$` — so `--help`, log output and the console wizard all work from a packaged
`Chronicler.exe server`.

When there is no parent console — a double-click, or a detached service — the call fails
and the app carries on as a pure GUI app. Running from source is unaffected: the process
already owns a console, the call fails with `ERROR_ACCESS_DENIED`, and the working
streams are left alone.

This is what keeps it to one binary rather than shipping a separate console build
alongside the windowed one.

## Hidden imports

PyInstaller's static analysis misses anything imported by name. The list in the spec is
empirical — each entry is there because a build failed without it:

| Import | Needed by |
| ------ | --------- |
| `aiosqlite` | SQLAlchemy resolves the `sqlite+aiosqlite` dialect by string |
| `re._parser` | pulled in dynamically by `re` on 3.12 |
| `logging.config` | `logging.basicConfig` paths reached only at runtime |

Add to both the spec and `scripts/pack.sh` when a new one turns up.

## Troubleshooting a build

`flet pack --debug-console` produces a build that shows a Python console window, which is
the fastest way to see a traceback from a packaged app that dies on startup. Do not commit
a spec generated that way.
