# 049-L5_open_folder_thin_client

## "Open folder" on a thin client tries to open a server path

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: a confusing failure, and an extra server path disclosed. Change risk: very low. |
| reach | Thin clients |
| effort | XS |
| evidence | read in code |
| touches | `chronicler/desktop/views/transcript/view.py`, `chronicler/core/services/transcript_service.py`, `tests/chronicler/core/test_rpc.py` |

### description

`open_folder_clicked` (`view.py:402-407`) asks the server for `chronicle_directory` and
opens the answer locally. On a thin client that path does not exist on this machine.

### proposed fix

Hide the button on a thin client using `desktop_mode`, and remove `chronicle_directory`
from `expose`.

Done when the button is absent on a thin client, and the API surface count is updated.

### related tickets

- (BLOCKER) [025-S9_single_mode_enum](025-S9_single_mode_enum.md): uses `desktop_mode`
