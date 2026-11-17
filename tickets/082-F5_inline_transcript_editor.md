# 082-F5_inline_transcript_editor

## The transcript editor looks like a form, not like the transcript

### info

| | |
| --- | --- |
| importance | medium |
| danger level | None: the editor works, but it does not read like a transcript and builds far more controls than it needs. Change risk: medium, because it replaces the editor's whole row layout. |
| reach | Everyone who corrects a transcript, in all modes |
| effort | M |
| evidence | read in code; Flet 0.86.5 APIs checked in the installed package; PR #92's client findings |
| touches | `chronicler/desktop/views/transcript/editor.py`, `chronicler/desktop/views/transcript/view.py`, `chronicler/desktop/theme.py`, `chronicler/i18n/messages/*.py`, `tests/chronicler/desktop/views/transcript/test_editor.py`, `docs/transcript-editing.md`, `docs/desktop.md` |

### description

Edit mode shows one row of form controls per line: a timestamp, a searchable speaker
dropdown, a bordered multi-line text field and a delete button. A screen of it looks like
a settings page, not like the conversation being corrected, and nothing about it suggests
that you are editing text. Every row also builds a dropdown with every workspace speaker
as an option.

### proposed fix

Build this on 056 (PR #92), which already shows the rows a window at a time and handles
saves around rows being replaced. Keep edit mode as a separate view behind the existing
toggle, but render each line the way the reading view does, and swap a part for its
control only when it is clicked. The design, including what is kept from #92 and why, is
in
[docs/superpowers/specs/2026-11-13-inline-transcript-editor-design.md](../docs/superpowers/specs/2026-11-13-inline-transcript-editor-design.md).

In short:

- **A row** is one `ft.Text` in `TRANSCRIPT_STYLE` with three spans: timestamp (muted,
  monospace), `Speaker: ` and the text, wrapping like the reader's. The row is a
  `Container` that tints on hover, keyed by line id. Rows sit with no gap between them
  (`ListView(spacing=0)`). The delete button shows only on the hovered row and on the row
  with an open control.
- **Clicking the text** (`TextSpan.on_click`) swaps in a borderless multi-line `TextField`
  in the same text style, focused with `focus()`. Enter saves and closes, Shift+Enter adds
  a newline, Esc discards and closes, and blur saves and closes.
- **Clicking the speaker** swaps in an editable `Dropdown` that opens empty with the
  current name as `hint_text`, so the name never looks gone. Its options are built now,
  for this picker only. Picking an option saves and closes. Leaving without picking saves
  nothing, even if something was typed.
- **One part is open at a time.** Opening another closes the open one first. Closing
  reads the control's value and saves it explicitly: Flet sends no blur for a field that
  is removed (found in #92), so nothing may depend on the blur. Esc clears the open part
  before the swap, and every blur and submit handler ignores a control that is no longer
  the open one, so a late blur cannot save a discarded edit.
- **#92's `save_unsaved()`** shrinks to closing the open control. It still runs before
  paging, the reload after a delete, and leaving edit mode. Esc is handled through
  `page.on_keyboard_event`, installed only while edit mode is showing.
- **#92's save handling stays**: the line takes the value when its save starts, a failure
  is undone when the field's last save ends, and the message names the line by its time.
  `_settle` repaints the row's spans instead of a text field.
- The timestamp is never clickable, and is always shown in edit mode.

The reading view, the edit toggle, the window and pager, opening on the first find match,
and disabling find and timestamps while editing all stay as they are.

Done when edit mode reads like the reading view apart from the timestamp and the hover,
each part opens its control on click and closes back to text, no edit is lost when a
control is closed by opening another part, paging or leaving edit mode, and a window
builds no dropdown options until a speaker is clicked. Record in
`docs/transcript-editing.md` what was confirmed by hand: span clicks and their cursor,
and Enter in the picker.

### related tickets

- (BLOCKER) [056-P5_editor_windowing](056-P5_editor_windowing.md): PR #92. 082 builds on its window, pager and save handling
- (BLOCKER) [086-L19_dropdown_clears_on_click](086-L19_dropdown_clears_on_click.md): same file in `widgets.py`, and the same lesson for the picker
- (BLOCKER) [036-S13_desktop_helpers](036-S13_desktop_helpers.md): moves the editor's update guard into `widgets.py`; take it first so this does not rewrite the same lines. A scheduling choice: see the design's ticket order
- (BLOCKER) [041-S3_services_bundle](041-S3_services_bundle.md): conflicts with most open desktop work, so it goes first. Same caveat as 036
- (BLOCKS) [084-F6_new_speaker_in_editor](084-F6_new_speaker_in_editor.md)
- (BLOCKS) [085-F7_editor_keyboard_flow](085-F7_editor_keyboard_flow.md)
- (RELATED) [058-T6_ui_rendering_checks](058-T6_ui_rendering_checks.md): hover and focus can only be checked by hand until that exists
