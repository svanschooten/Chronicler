# 001-C1_sqlalchemy_asyncio_extra

## A fresh install cannot start

### info

| | |
| --- | --- |
| importance | critical |
| danger level | High: nothing runs after a clean install. Change risk: very low. |
| reach | Every source install, the PyInstaller release job, and CI on its next cache miss |
| effort | XS |
| evidence | reproduced |
| touches | `pyproject.toml`, `.github/workflows/release-workflow.yml` |

### description

`pyproject.toml:30` declares `SQLAlchemy>=2.0.52,<3`, which now resolves to 2.1.8.
SQLAlchemy 2.1 no longer installs `greenlet`, and the app imports `sqlalchemy.ext.asyncio`
at startup, so it fails immediately.

```text
$ pip install -e ".[dev,server]"    # resolves SQLAlchemy 2.1.8, no greenlet
ImportError: The SQLAlchemy asyncio module requires that the Python 'greenlet' library is installed.
```

The embedded-runtime build is safe because `base.lock` pins 2.0.54 with greenlet. Source
installs, the PyInstaller job (`release-workflow.yml:86` installs unpinned) and CI as soon
as its venv cache misses are all exposed. The release job's verification step
(`release-workflow.yml:90`) only imports the extras, so it would not catch this.

With greenlet added by hand, the test suite on 2.1.8 gave the same result as the pinned
set, so 2.1 appears otherwise compatible.

### proposed fix

1. Change the dependency to `"SQLAlchemy[asyncio]>=2.0.52,<3"`.
2. Run `python scripts/runtime/locks.py` and commit anything it changes, since CI checks
   the locks against `pyproject.toml`.
3. Add `chronicler.desktop.main` to the import check in `release-workflow.yml:90`, so a
   broken base install fails the release.

Done when a new virtualenv with `pip install -e ".[dev,server]"` can run `python -c
"import chronicler.desktop.main"`.

### related tickets

- (BLOCKS) [002-T2_two_connection_test_fixture](002-T2_two_connection_test_fixture.md): needs a working install
- (BLOCKS) [003-T1_windows_test_portability](003-T1_windows_test_portability.md): needs a working install
- (BLOCKS) [004-S12_ci_and_install_cleanup](004-S12_ci_and_install_cleanup.md): CI reinstalls dependencies as soon as its cache key changes
- (BLOCKS) [016-H1_server_component_for_binaries](016-H1_server_component_for_binaries.md): the PyInstaller job installs unpinned
