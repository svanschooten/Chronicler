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
silently drops it — which is exactly what happened to the comments in it once. The script
now writes those back after `flet pack` runs, and fails if `flet pack` ever stops emitting
`console=False`, so the one setting the app depends on cannot be lost quietly.

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

## The three Flet packages

`flet` on its own cannot open a window, and this is the trap the release workflow fell
into: it declares `flet-desktop` as an **extra**, not a dependency.

| Package | Needed for | Installed by |
| ------- | ---------- | ------------ |
| `flet` | the framework | `pip install .` |
| `flet-desktop` | opening the window at runtime | the `flet[desktop]` extra in `pyproject.toml` |
| `flet-cli` | the PyInstaller hook that bundles the client | the workflow's install step |

Running from source hid the gap. `flet.run()` tries to `pip install flet-desktop` when the
module is missing, which quietly works in a virtualenv — so a developer machine that has
ever run the app has the package, and packs a working binary. A CI runner has neither the
package nor a virtualenv to install it into, so the binary it produced died on launch with
`ModuleNotFoundError: No module named 'flet_desktop'` (followed by `NameError: name 'exit'
is not defined`, which is only PyInstaller's frozen build having no `site` builtins to
report the first error with).

`flet-cli` is a build-time dependency, not a runtime one. It registers a `pyinstaller40`
entry point, which is how `hook-flet.py` gets discovered and run — nothing in the spec
refers to it. Without it PyInstaller still produces a binary; it is just missing the
client, about 38 MB smaller, and unable to start on a machine with no `~/.flet` cache.

## The client is bundled, and has to be pointed at

`hook-flet.py` copies the Flet client into the bundle as `flet_desktop/app/`. Flet does
not then use it: `ensure_client_cached()` looks in that directory for a *downloaded
archive*, while the hook puts an *extracted tree* there, so the check misses and the app
downloads its own copy into `~/.flet` on first run.

`use_bundled_flet_client()` in `desktop/main.py` closes that gap by setting
`FLET_VIEW_PATH` to the bundled client before `ft.run()`. Without it every user who
downloads a release pays for a client download on first launch — silently, because a
windowed build has nowhere to print the progress bar, and fatally if they are offline.

It only acts on a frozen build, and never overrides an `FLET_VIEW_PATH` that is already
set, which is how `flet build` output is normally tried out.

## Hidden imports

PyInstaller's static analysis misses anything imported by name. The list in the spec is
empirical — each entry is there because a build failed without it:

| Import | Needed by |
| ------ | --------- |
| `aiosqlite` | SQLAlchemy resolves the `sqlite+aiosqlite` dialect by string |
| `re._parser` | pulled in dynamically by `re` on 3.12 |
| `logging.config` | `logging.basicConfig` paths reached only at runtime |

Add to both the spec and `scripts/pack.sh` when a new one turns up.

## Building one locally

```bash
pip install -e . flet-cli pyinstaller
pyinstaller Chronicler.spec
```

One `pip install` for all three keeps the Flet versions in step: `flet-cli` pins `flet` to
its own version, and the `desktop` extra pins `flet-desktop` to whatever `flet` resolves
to. Installing them separately can leave a skew.

The first build on a machine with no `~/.flet` cache downloads the client, because the
hook needs a copy to bundle. That is a build-time download only.

The binary lands in `dist/` — `dist/Chronicler` on Linux, `dist/Chronicler.exe` on
Windows. There is no separate build step for the two; the same spec covers both.

Worth checking on a fresh Windows build, because none of it can be exercised from CI or
from Linux:

* double-clicking `Chronicler.exe` opens the window with **no console flashing up**, and
  with no config present shows the setup wizard rather than dying silently
* `Chronicler.exe --help` **from PowerShell** prints, rather than returning to the prompt
  with nothing — this is `attach_windows_console()` doing its job
* `Chronicler.exe server` from a terminal reaches the console wizard when unconfigured
* the folder picker on the workspace step opens a native dialog

On either platform, a release binary is only proven by running it somewhere that has never
had Flet installed — an empty `HOME` is enough. That is what catches a missing
`flet-desktop` or an unbundled client, and what a build on the developer's own machine
cannot catch, because its `~/.flet` cache papers over both.

## Releasing

The version is written in exactly one place, `chronicler/__init__.py`. Hatchling reads it
from there via `[tool.hatch.version]`, so the wheel filename, the package metadata and
`chronicler.__version__` — which the thin-client handshake compares across the wire — all
follow that single line.

1. Edit `__version__` in `chronicler/__init__.py`.
2. Commit, tag, push the tag.
3. Publish the GitHub release for that tag. That fires `release-workflow.yml`, which
   builds both binaries from the spec and attaches them to the release.

**The tag decides what gets built.** The workflow's `version` job reads the release tag,
strips a leading `v` if there is one (`v1.0.9` and `1.0.9` both land as `1.0.9`), and
`pack` stamps that number over `__version__` in its own checkout before running
PyInstaller. So step 1 is what keeps the source honest, but forgetting it cannot ship a
binary that reports the wrong version — the tag wins. Nothing is committed back; the
branch only tracks the version because you edited it.

A tag that is not three dot-separated numbers after the `v` fails the job on purpose —
`tests/chronicler/test_basic.py` asserts `__version__` matches `\d+\.\d+\.\d+`, and the
handshake's version comparison assumes the same shape. Prereleases like `v2.0.0-rc1`
would need both of those loosened first.

`tests/chronicler/test_basic.py` fails if a second version literal is ever added back to
`pyproject.toml`, which is how this stayed in four files before.

Everything that reports a version — the handshake, `ServerInfo`, the sidebar — imports
`chronicler.__version__` rather than asking `importlib.metadata`. Metadata would be wrong
in both directions that matter: an editable install bakes the number in at install time
and goes stale the moment you bump it, and a PyInstaller build has no dist-info to read
at all.

## Troubleshooting a build

`flet pack --debug-console` produces a build that shows a Python console window, which is
the fastest way to see a traceback from a packaged app that dies on startup. Do not commit
a spec generated that way.
