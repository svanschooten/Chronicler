# 026-M9_stale_mode_crashes_desktop

## A web-client config crashes the desktop app

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Medium: an unhandled error at startup. Change risk: none beyond the linked ticket. |
| reach | Anyone with a `client:web` configuration who launches the desktop |
| effort | none beyond the linked ticket |
| evidence | reproduced |
| touches | `chronicler/core/config.py:143-148`, `chronicler/desktop/runtime.py:28-48` |

### description

With `mode: client:web` plus a server URL and key, `validate_for_mode("client:desktop")`
passes, so the wizard is skipped. `build_runtime` then raises `ValueError:
desktop:full_stack mode requires settings.workspace_path` inside the Flet session.

### related tickets

- (CLOSED BY) [025-S9_single_mode_enum](025-S9_single_mode_enum.md): validation and runtime building share one answer
