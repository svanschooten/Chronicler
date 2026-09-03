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
