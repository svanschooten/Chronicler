# Testing

`tests/` mirrors the package tree module for module, so the tests for
`chronicler/core/processing/handlers/importing.py` live in
`tests/chronicler/core/processing/handlers/test_importing.py`. The directories are real
packages (`__init__.py`) because the mirrored layout repeats module names.

## Shared fixtures

| Fixture | Defined in | Purpose |
| ------- | ---------- | ------- |
| `async_session` | `tests/conftest.py` | An in-memory workspace database session |
| `two_sessions` | `tests/conftest.py` | A file-backed workspace with two independent sessions on `chronicler.db`, for lock contention |
| `mock_flet_app` | `tests/conftest.py` | Autouse; stops anything from opening a real window |
| `attach_page` | `tests/chronicler/desktop/conftest.py` | Gives a Flet control a stand-in `page`, since `Control.page` is a read-only property that raises when unattached |
| `tester` | `tests/ui/conftest.py` | The desktop app on a seeded workspace, drawn by a real Flutter client; see [Rendered UI tests](#rendered-ui-tests) |

`tests/paths.py` holds repo-relative paths for fixture files, so no test walks
`parents[n]` to find one. `tests/chronicler/desktop/controls.py` has helpers for
asserting against a built Flet control tree.

## How views are tested

Views are tested by building them and inspecting the controls they produced. Nothing
renders. Logic worth testing without a page attached is deliberately kept out of the
views — `ImportCoordinator` is the clearest example.

A control tree cannot show what the Flutter client actually draws, so a few flows also
run against the real client: see [Rendered UI tests](#rendered-ui-tests).

## Rendered UI tests

`tests/ui/` runs the desktop app in full-stack mode on a seeded workspace and drives a
real Flutter client through `flet.testing`: finding text and tooltips, tapping, typing.
The `tester` fixture in `tests/ui/conftest.py` starts both, and fails any test that
leaves "Unknown control" on screen, which is what the client draws for a control it
cannot render. The FilePicker that was once added to `page.overlay` did that, and no
control-tree test could see it.

They are slow, about 25 seconds a test, since each starts its own `flutter test`. Keep
them to flows a control tree cannot check: what is on screen after a click, a dialog
that closes, an edit that shows up.

**The client.** `flet.testing` in host mode needs a Flutter app to connect from.
`scripts/ui_host.py` fetches Flet's own `client/` at the tag of the installed Flet and
trims it. It removes every Flet extension, which Chronicler does not use and which need
system libraries for video, maps and web views. It also lifts Flet's `jni: 1.0.0`
override to `^1.1.1`, without which `flutter pub get` fails on current packages. Flet
pins it for an ARM64 build bug, dart-lang/native#3498. Drop the override once that is
fixed.

**Running them.** They are only collected when `FLET_TEST_FLUTTER_APP_DIR` is set, so
the ordinary `pytest` run skips the folder. On Linux, with `clang ninja-build
libgtk-3-dev xvfb` from apt and the Flutter version the installed Flet names
(`python scripts/ui_host.py --flutter-version`) on `PATH`:

```bash
pip install "flet[test]==$(python -c 'from importlib.metadata import version; print(version("flet"))')"
```

```bash
export FLET_TEST_FLUTTER_APP_DIR=$(python scripts/ui_host.py build/ui-host)
```

```bash
GDK_BACKEND=x11 LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a -s "-screen 0 1600x1000x24" pytest tests/ui
```

Without `GDK_BACKEND=x11 LIBGL_ALWAYS_SOFTWARE=1` the tests still pass on Xvfb but
nothing is drawn. Under WSL, also unset `WAYLAND_DISPLAY`. The first run builds the
client, which takes about a minute.

**Screens of failures.** Flet takes app screenshots only on Android and iOS. Set
`CHRONICLER_UI_SCREENSHOTS` to a folder, with `ffmpeg` installed, and the fixture grabs
the X display there when a test fails.

**Flutter's package cache.** Every test points `HOME` at a temporary folder, and Flutter
keeps its packages under `HOME`. The conftest sets `PUB_CACHE` to the real cache first,
or every test downloads the packages again into a folder pytest later deletes.

## Isolation from the developer's machine

Config tests isolate both `user_config_dir` **and** `Path.home()`. Isolating only the
first meant `Settings()` inside a test read the real `~/.chronicler_config.yaml` if one
existed. That was masking a wrong assertion: `test_desktop_mode_requires_either`
asserted that a thin client with no API key validates, which is false — it only passed
because the real config supplied a key.

## Gates

CI installs with `pip install -e ".[dev,server]"` and runs these checks, in order:

```bash
ruff check chronicler tests
```

```bash
ruff format --check chronicler tests
```

```bash
mypy chronicler tests
```

```bash
pytest --cov=chronicler --cov-report=term --cov-fail-under=80
```

The tests run on Ubuntu and Windows; the other checks run once, on Ubuntu.
All of them are blocking, with no per-module exemptions. The **Rendered UI** job runs
`tests/ui/` on Ubuntu 24.04, not `ubuntu-latest`: the Mesa on the newer image (26.0)
segfaults in its software renderer when the Flutter client draws under `flutter test`.
The job is not blocking until it has shown it is not flaky; when it
fails, it uploads a grab of the screen for each failed test. Prefer a narrow
`# type: ignore[code]` over widening the configuration. Run `ruff format chronicler tests`
before pushing to clear a formatting failure.

Every job sets up through `.github/actions/setup`, so a new job or platform reuses that
one step instead of repeating the install.

## Leaked connections fail the run

`ResourceWarning` is an error in `filterwarnings`, and so is the warning pytest raises
when one comes out of a destructor. A database connection or file left open is a test
failure rather than a line in the warnings summary: before this, a session leak hid in
that summary for a whole sprint.

The failure lands in whichever test the garbage collector happens to collect the object
in, which is usually not the test that leaked it. To find the real one, record where each
connection is opened, for example by wrapping `aiosqlite.core.Connection.__init__` in a
throwaway plugin that saves `traceback.format_stack()` and prints it from `__del__`.
`PYTHONTRACEMALLOC=20` does the same for plain files.

The usual causes: a `DatabaseManager` with no `close_all()` (give it a fixture that
closes it), and `with sqlite3.connect(...)`, which commits but does not close. Use
`with closing(sqlite3.connect(...)) as connection, connection:` for both.

The guard only sees what Python warns about. Files and `aiosqlite` connections warn on
Python 3.12, which CI runs. A plain `sqlite3` connection warns only from Python 3.13, so
on 3.12 an unclosed one passes unnoticed: close it all the same.

`faster-whisper` is deliberately **not** installed in CI. It is an optional extra,
imported lazily, and ships no `py.typed` marker, so mypy has an `ignore_missing_imports`
override for it.

## Keeping the developer's own configuration out of the tests

`isolated_config` in `tests/conftest.py` points the home directory, the per-user config
directory and `CHRONICLER_CONFIG_FILE` at a temporary directory and clears the
`get_settings` cache. The first two go through `isolate_home` in `tests/isolation.py`,
which sets `USERPROFILE` as well as `HOME` because Windows ignores `HOME`, and patches
platformdirs' `user_config_dir` because on Windows it asks the OS for `AppData` rather
than reading the environment. Any test that builds a
`Settings()` needs it, or it reads whatever is on the machine running it and passes or
fails accordingly — which is how a transcribe-dialog test asserting the default language
is `auto` failed on a laptop with `en` configured.

It started as two near-identical copies in `test_config.py` and `test_wizard_defaults.py`.
`test_config.py` keeps its own override on purpose: it tests the default config-file
*search*, so it must not have an explicit file forced on it. It still calls
`isolate_home`.

**It is autouse, for every test.** Any test that constructs a bare `Settings()` needs it,
not just the ones about configuration, and opting in kept being forgotten. The task-handler
tests build one to get the shipped defaults, and without isolation they got the
developer's instead — on a machine with a real language model configured,
`test_an_unconfigured_provider_fails_clearly` stopped testing anything and sent a live
request to that provider. Those modules each grew an autouse wrapper, and two view and
runtime tests that had none still read the developer's workspace and failed on any machine
with one configured (ticket 071). The home directory is made with `tmp_path_factory`
rather than inside `tmp_path`, so a test asserting its `tmp_path` is empty still can.

A test that starts a child Python process from the source install opts out with
`@pytest.mark.real_home` (as `tests/scripts/runtime/test_smoke.py` does): a moved HOME
hides a `pip install --user` of the dependencies from the child. Such a test must keep the
developer's configuration out some other way, for example by passing `--config`.

## Extras that may not be installed

A test module that needs an optional extra starts with:

```python
from tests.extras import require_extra

require_extra("normalization")
```

It imports every module the extra provides (`extras.get_extra(name).modules`) with
`pytest.importorskip(..., exc_type=ImportError)` and skips the module with the reason
"requires the 'normalization' extra". `exc_type=ImportError` matters for more than the
pytest 9.1 deprecation: it makes the skip mean "cannot be imported" rather than "is
absent", which is the same distinction `extras.is_available()` draws.

Always go through `require_extra`. The *Tests With Every Extra* CI job installs every
runtime lock and fails on a skip with exactly that wording, so a skip worded any other way
would hide an extra that the locks failed to provide. `tests/test_extras_skips.py` fails on
an `importorskip` anywhere but `tests/extras.py`. An extra with no runtime lock (`llm`)
would fail that job, so its tests cannot use `require_extra` until it has one.

CI installs no extras, so verifying that locally means hiding them. A directory of
`av.py` / `faster_whisper.py` modules that raise `ImportError`, put first on
`PYTHONPATH`, reproduces CI faithfully and is stricter than absence — it also covers the
installed-but-unimportable case. That check is what caught a test asserting
`is_available()` should agree with `find_spec()`, which contradicts the whole reason
`is_available()` imports for real.

## The guard against untranslated strings

`tests/chronicler/i18n/test_no_bare_strings.py` walks the AST of every module under
`chronicler/desktop/` and fails on a bare string literal in a user-facing position:
`ft.Text(...)`, `ft.SnackBar(...)`, and the `label` / `hint_text` / `tooltip` /
`helper_text` / `error` / `error_text` keywords.

The catalogue-integrity tests cannot catch this. They check that keys which *are* used
exist and that the translations agree — not that a string reaches the user through `t()`
at all. Three whole views were hardcoded English while the catalogue already held their
keys, and nothing failed. Adding this guard immediately turned up three more cases beyond
the ones the audit had listed by hand.

It parametrises over modules rather than asserting once, so a failure names the file, and
carries a `test_there_are_desktop_modules_to_check` guard so a bad glob cannot make every
case pass vacuously. `ALLOWED` holds the handful of literals that are genuinely not
language — separators, `"monospace"`.

## Simulating a locked database

`async_session` is one in-memory connection, so nothing in it can ever wait on a lock.
Tests for "database is locked" use `two_sessions` instead: a flushed, uncommitted write in
`first` holds the write lock, and a write in `second` raises `OperationalError`.

Its `DatabaseManager` is built with `busy_timeout=LOCK_TIMEOUT` (0.2 seconds), so that
error arrives quickly rather than after SQLite's default 5 seconds. Pass
`two_sessions.db_manager` to code under test that opens its own sessions, such as the
worker, and those sessions get the same short timeout.
`test_a_second_writer_fails_fast_while_the_first_holds_the_lock` is the reference example.
