# 036-S13_desktop_helpers

## Share the desktop's repeated helpers

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: maintenance cost only. Change risk: very low. |
| reach | Internal. About 40 lines |
| effort | XS |
| evidence | read in code |
| touches | `chronicler/desktop/widgets.py`, `chronicler/desktop/views/settings/view.py`, `chronicler/desktop/views/transcript/editor.py`, `recording.py`, `transcribe_dialog.py`, `view.py`, `chronicler/desktop/views/archive/view.py`, `chronicler/desktop/views/wizard.py` |

### description

The update guard `try: control.update() except (RuntimeError, AssertionError)` appears 8
times across 6 files. FilePicker registration in `did_mount` and `will_unmount` appears in
4 views.

### related tickets

- none
