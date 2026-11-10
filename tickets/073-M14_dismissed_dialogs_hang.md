# 073-M14_dismissed_dialogs_hang

## Dismissing a dialog leaves its action waiting forever, and a recording keeps running

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Medium: a microphone the user believes is off keeps recording, and recordings pile up in the system temp folder. Change risk: low. |
| reach | Desktop, all modes. Every dialog built on `await_dialog` |
| effort | S |
| evidence | read in code, and in Flet 0.86.5's `AlertDialog` and `Page.show_dialog` |
| touches | `chronicler/desktop/dialogs.py`, `chronicler/desktop/views/transcript/recording.py`, `tests/chronicler/desktop/test_dialogs.py`, `tests/chronicler/desktop/views/transcript/test_recording.py`, `docs/desktop.md`, `docs/recording.md` |

### description

Found in the review after wave 4.

No dialog in the app sets `modal=True`, and Flet's default is `False`, so clicking
outside a dialog or pressing Esc closes it. `await_dialog` (`dialogs.py:22-41`) only
resolves its future from a button handler and never sets `on_dismiss`. A dismissed
dialog therefore leaves the code awaiting it suspended for the life of the app.

`ask_choice`, `confirm` and the recording dialog go through it: 11 call sites in 7 files,
including the extras install prompt, deleting a line, a summary or a chronicle, and the
overwrite-or-append question. For
most of them the action is silently abandoned: the overwrite-or-append question leaves its
staged file in `imports/`, for example.

For recording it is worse. `RecordingDialog.run` (`recording.py:57-102`) only stops the
recorder after `await_dialog` returns, which never happens. The dialog is gone and the
microphone keeps recording until the app exits.

Separately, `_start` writes each recording into its own `tempfile.mkdtemp` folder
(`recording.py:105`) that nothing removes, even after a successful save:
`LocalFileStager` copies the file rather than moving it (`file_staging.py:37-44`). Every
recording stays in the system temp folder.

### proposed fix

1. Have `await_dialog` take the value a dismissal means, and resolve the future with it
   from the dialog's `on_dismiss`: the cancel choice for `ask_choice` and `confirm`,
   `None` for `ask_text`, and *Close* for the recording dialog.
2. Stop the recorder in a `finally` around the dialog.
3. Remove the recording's temp folder once it is saved or discarded.

Making every dialog modal would also stop the hang, but Esc closing a dialog is expected
behaviour, so resolving on dismiss is the better fix.

Done when a test fires a dialog's `on_dismiss` and the awaiting call returns the cancel
value, and closing the recording dialog by dismissal leaves the recorder stopped and no
temp folder behind.

### related tickets

- (RELATED) [036-S13_desktop_helpers](036-S13_desktop_helpers.md): edits `recording.py` too
- (RELATED) [058-T6_ui_rendering_checks](058-T6_ui_rendering_checks.md): a bug only a real rendered dialog shows
- (RELATED) [047-L3_finish_translation](047-L3_finish_translation.md): the default labels in `dialogs.py` are untranslated
