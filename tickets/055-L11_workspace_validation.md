# 055-L11_workspace_validation

## Workspace validation exists but never runs

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: an unwritable workspace fails later and less clearly. Change risk: very low. |
| reach | Full stack and server |
| effort | XS |
| evidence | scanned |
| touches | `chronicler/core/config.py`, `chronicler/desktop/main.py`, `chronicler/server/main.py` |

### description

`Settings.is_workspace_valid` (`config.py:129`) is never called in production, though
`TODO.md` marks workspace validation done. It uses `os.access`, which is unreliable on
Windows.

### proposed fix

Call it when opening the workspace, and report a failure the same way as a failed lock.
Test by writing a probe file instead of `os.access`.

Done when an unwritable workspace gives a clear startup message.

### related tickets

- (RELATED) [008-A1_single_process_workspace_lock](008-A1_single_process_workspace_lock.md): reports failure through the same startup path
- (RELATED) [003-T1_windows_test_portability](003-T1_windows_test_portability.md): that ticket deals with this method's Windows test
- (RELATED) [029-S1_remove_dead_code](029-S1_remove_dead_code.md): that ticket leaves this method alone
