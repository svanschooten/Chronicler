# Testing

`tests/` mirrors the package tree module for module, so the tests for
`chronicler/core/processing/handlers/importing.py` live in
`tests/chronicler/core/processing/handlers/test_importing.py`. The directories are real
packages (`__init__.py`) because the mirrored layout repeats module names.

## Shared fixtures

| Fixture | Defined in | Purpose |
| ------- | ---------- | ------- |
| `async_session` | `tests/conftest.py` | An in-memory workspace database session |
| `mock_flet_app` | `tests/conftest.py` | Autouse; stops anything from opening a real window |
| `attach_page` | `tests/chronicler/desktop/conftest.py` | Gives a Flet control a stand-in `page`, since `Control.page` is a read-only property that raises when unattached |

`tests/paths.py` holds repo-relative paths for fixture files, so no test walks
`parents[n]` to find one. `tests/chronicler/desktop/controls.py` has helpers for
asserting against a built Flet control tree.

## How views are tested

Views are tested by building them and inspecting the controls they produced. Nothing
renders. Logic worth testing without a page attached is deliberately kept out of the
views — `ImportCoordinator` is the clearest example.

## Isolation from the developer's machine

Config tests isolate both `user_config_dir` **and** `Path.home()`. Isolating only the
first meant `Settings()` inside a test read the real `~/.chronicler_config.yaml` if one
existed. That was masking a wrong assertion: `test_desktop_mode_requires_either`
asserted that a thin client with no API key validates, which is false — it only passed
because the real config supplied a key.

## Gates

The three checks CI runs, in order:

```bash
ruff check chronicler tests
```

```bash
mypy chronicler tests
```

```bash
pytest --cov=chronicler --cov-report=term --cov-fail-under=80
```

`ruff` and `mypy` are blocking with no per-module exemptions. Prefer a narrow
`# type: ignore[code]` over widening the configuration.

`ruff format` is advisory only and reported as a PR comment rather than a gate:
formatting was never enforced, so drift predates any one PR and failing on it would
block unrelated work.

`faster-whisper` is deliberately **not** installed in CI. It is an optional extra,
imported lazily, and ships no `py.typed` marker, so mypy has an `ignore_missing_imports`
override for it.

## Keeping the developer's own configuration out of the tests

`isolated_config` in `tests/conftest.py` points `HOME` and `CHRONICLER_CONFIG_FILE` at a
temporary directory and clears the `get_settings` cache. Any test that builds a
`Settings()` needs it, or it reads whatever is on the machine running it and passes or
fails accordingly — which is how a transcribe-dialog test asserting the default language
is `auto` failed on a laptop with `en` configured.

It started as two near-identical copies in `test_config.py` and `test_wizard_defaults.py`.
`test_config.py` keeps its own override on purpose: it tests the default config-file
*search*, so it must not have an explicit file forced on it.

## Extras that may not be installed

Tests that decode real audio call:

```python
pytest.importorskip("av", reason="requires the 'normalization' extra", exc_type=ImportError)
```

`exc_type=ImportError` matters for more than the pytest 9.1 deprecation: it makes the
skip mean "cannot be imported" rather than "is absent", which is the same distinction
`extras.is_available()` draws.

CI installs no extras, so verifying that locally means hiding them. A directory of
`av.py` / `faster_whisper.py` modules that raise `ImportError`, put first on
`PYTHONPATH`, reproduces CI faithfully and is stricter than absence — it also covers the
installed-but-unimportable case. That check is what caught a test asserting
`is_available()` should agree with `find_spec()`, which contradicts the whole reason
`is_available()` imports for real.
