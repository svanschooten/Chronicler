# 059-S15_retire_pyinstaller

## Retire the PyInstaller build

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Low: two release pipelines to maintain, one of them unpinned. Change risk: medium, changes what users download. |
| reach | Everyone who downloads a release. About 150 lines |
| effort | S |
| evidence | read in code; sizes from `docs/runtime-build.md` |
| touches | `Chronicler.spec`, `scripts/pack.sh`, `.github/workflows/release-workflow.yml`, `chronicler/core/extras.py`, `chronicler/desktop/main.py`, `chronicler/__main__.py`, `docs/packaging.md`, `docs/runtime-build.md`, `README.md` |

### description

Decision from the audit: retire PyInstaller after one release of the runtime build. **Do
not start until that release has been used.**

The runtime build is smaller (59 MB against 164 MB on Linux, per `docs/runtime-build.md`),
starts faster, is hash-pinned and can add features later. The PyInstaller job is unpinned,
which is what exposes it to the install failure. `pack.sh` regenerates the spec and then
re-inserts its comments with embedded Python.

### proposed fix

1. Delete `Chronicler.spec`, `scripts/pack.sh` and the `pack` job.
2. Remove the `is_frozen` and `_MEIPASS` paths (`extras.py:117-121`,
   `desktop/main.py:50-56`).
3. Check whether `attach_windows_console` is still needed. The runtime ships a separate
   console executable for server use, so it probably is not.
4. Rename the release assets, and merge what still applies from `docs/packaging.md` into
   `docs/runtime-build.md`.

Done when a release produces only runtime builds, and a fresh Windows machine can start
one.

### related tickets

- (BLOCKER) [016-H1_server_component_for_binaries](016-H1_server_component_for_binaries.md): the runtime build must run a server first
- (RELATED) [016-H1_server_component_for_binaries](016-H1_server_component_for_binaries.md): if PyInstaller is retired first, step 5 is unnecessary
