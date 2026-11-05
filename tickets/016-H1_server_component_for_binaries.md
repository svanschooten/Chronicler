# 016-H1_server_component_for_binaries

## Released binaries ship without server mode

### info

| | |
| --- | --- |
| importance | high |
| danger level | Medium: a documented mode fails at startup. Change risk: low. |
| reach | Anyone running `Chronicler server` or `Chronicler-modular-cli server` from a release |
| effort | S |
| evidence | inferred from the lock files and release workflow; no binary was built |
| touches | `scripts/runtime/pins.py`, `scripts/runtime/locks/`, `scripts/runtime/smoke.py`, `chronicler/core/extras.py`, `chronicler/__main__.py`, `.github/workflows/release-workflow.yml`, `tests/chronicler/core/test_extras.py`, `docs/optional-extras.md`, `docs/runtime-build.md` |

### description

FastAPI, Uvicorn and python-multipart live only in the `server` extra. The PyInstaller job
installs `.[transcription,normalization,recording] flet-cli pyinstaller`
(`release-workflow.yml:86`), and flet-cli's 36-package dependency closure contains none of
them. No lock file contains them either. So `Chronicler.exe server` should reach the
wizard and then fail on `import uvicorn` (`server/main.py:5`).

`HOWTO.md:12`, `docs/packaging.md:50` and `docs/runtime-build.md:19` all promise this
mode. `smoke.py` never starts it, so CI would not notice.

From source, a missing `[server]` extra also gives a raw traceback, because
`core/extras.py` does not list it.

Decision from the audit: packaged builds should run a server, as a downloadable component.

### proposed fix

1. Add `server` to `COMPONENTS` in `scripts/runtime/pins.py:121` and regenerate the locks.
2. Register it in `EXTRAS`. `Extra.requirement` is a single string and this extra has
   three packages, so it needs a small change, and the tests that expect four extras need
   updating.
3. Guard `server_main` with `extras.is_available("server")` and print `missing_message`
   instead of a traceback.
4. Have `smoke.py` start the server on a free port with a temporary config and call
   `/system/ping`.
5. Add `server` to the PyInstaller install while that job exists.

Done when the smoke test boots a server from the built runtime and gets a response.

### related tickets

- (BLOCKER) [001-C1_sqlalchemy_asyncio_extra](001-C1_sqlalchemy_asyncio_extra.md): the PyInstaller job installs unpinned
- (BLOCKER) [012-S14_remove_web_client](012-S14_remove_web_client.md): only server mode needs to be packaged once the web client is gone
- (BLOCKS) [059-S15_retire_pyinstaller](059-S15_retire_pyinstaller.md): the runtime build must run a server first
- (RELATED) [059-S15_retire_pyinstaller](059-S15_retire_pyinstaller.md): if PyInstaller is retired first, step 5 is unnecessary
