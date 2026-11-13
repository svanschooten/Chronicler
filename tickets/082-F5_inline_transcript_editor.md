# 082-F5_inline_transcript_editor

## The transcript editor looks like a form, not like the transcript

### info

| | |
| --- | --- |
| importance | medium |
| danger level | None: the editor works, but it does not read like a transcript and builds far more controls than it needs. Change risk: medium, because it replaces the editor's whole row layout. |
| reach | Everyone who corrects a transcript, in all modes |
| effort | M |
| evidence | read in code; Flet 0.86.5 APIs checked in the installed package |
| touches | `chronicler/desktop/views/transcript/editor.py`, `chronicler/desktop/widgets.py`, `chronicler/i18n/messages/*.py`, `tests/chronicler/desktop/views/transcript/test_editor.py`, `docs/transcript-editing.md`, `docs/desktop.md` |

### description

Edit mode shows one row of form controls per line: a timestamp, a searchable speaker
dropdown, a bordered multi-line text field and a delete button. A screen of it looks like
a settings page, not like the conversation being corrected, and nothing about it suggests
that you are editing text.

It is also what ticket 056 measured. Every row builds its own dropdown with every
workspace speaker as an option, which comes to 18,546 control objects for the 1,686-line
example.

### proposed fix

Keep edit mode as a separate view behind the existing toggle, but render each line the
way the reading view does: timestamp, speaker and text as plain text, in the same font
and line height. Clicking a part of the line swaps that part, and only that part, for its
control. The design is in
[docs/superpowers/specs/2026-11-13-inline-transcript-editor-design.md](../docs/superpowers/specs/2026-11-13-inline-transcript-editor-design.md).

In short:

- A row is a container holding three texts: timestamp (monospace, muted, always shown),
  speaker (fixed width, bold) and text (expands). The row tints on hover and shows a
  click cursor, so you can see it can be clicked.
- Clicking the text puts a borderless multi-line `TextField` in its place with
  `autofocus`, `shift_enter=True` and the line's text. **Enter** saves and closes it,
  **Shift+Enter** adds a newline, **Esc** discards the edit and closes it, and **blur**
  saves, as it does today.
- Clicking the speaker puts a `searchable_dropdown` in its place, with `autofocus`. Its
  options are built at that moment, not when the row is built. Picking or typing a name
  saves it and closes the dropdown. Leaving without a change closes it with nothing saved.
- One control is open at a time. Opening another part closes the open one first, and an
  open text field saves on blur as it closes.
- The delete button appears only on the hovered row or the row being edited. Its
  confirmation is unchanged.
- The timestamp is never clickable. Timings are never touched (see
  `docs/transcript-editing.md`).
- The save rules stay as they are: save only on a real change, revert and show a snackbar
  when a save fails, never reload the list after a single-line save.

The reading view, the edit toggle and disabling find and timestamps while editing all
stay as they are.

Done when edit mode reads like the transcript, each part of a line opens its control on
click and closes back to text, and opening edit mode on the example builds no dropdown
options until a speaker is clicked.

### related tickets

- (CLOSES) [056-P5_editor_windowing](056-P5_editor_windowing.md): rows become a few text controls each, and dropdown options are built only for the speaker being edited
- (BLOCKER) [036-S13_desktop_helpers](036-S13_desktop_helpers.md): moves the editor's update guard into `widgets.py`; take it first so this does not rewrite the same lines
- (BLOCKER) [041-S3_services_bundle](041-S3_services_bundle.md): conflicts with most open desktop work, so it goes first
- (BLOCKS) [084-F6_new_speaker_in_editor](084-F6_new_speaker_in_editor.md)
- (BLOCKS) [085-F7_editor_keyboard_flow](085-F7_editor_keyboard_flow.md)
- (RELATED) [058-T6_ui_rendering_checks](058-T6_ui_rendering_checks.md): hover and focus can only be checked by hand until that exists
