# 086-L19_dropdown_clears_on_click

## Clicking a speaker or model picker empties it, and leaving does not always put it back

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Low: no data is lost, but a speaker or model looks deleted, and an untouched picker can stay blank. Change risk: low. |
| reach | The transcript editor's speaker pickers, the transcribe dialog's speaker, the summary model picker, in all modes |
| effort | XS |
| evidence | reported in use; read in code; Flet 0.86.5 checked in the installed package |
| touches | `chronicler/desktop/widgets.py`, `tests/chronicler/desktop/test_widgets.py`, `docs/desktop.md` |

### description

`searchable_dropdown()` empties its field on focus (`clear_for_typing` sets `value` to
`None`), so typing filters the list instead of being inserted into the current name. That
is deliberate, but the result is that clicking a picker makes its name disappear. In the
transcript editor this reads as the click deleting the line's speaker.

Leaving the field is meant to put the name back. `restore_if_nothing_chosen` does so only
when `control.text` is empty. `text` is reported by the client and is not written by the
server (`docs/desktop.md`), so once the field has reported any text it can still hold that
earlier value after the clear. The restore is then skipped, and the field stays blank
although nothing was chosen.

Only a click on the field focuses it. A click on the arrow of an untouched field opens the
menu without focusing it (found in PR #92), so the same picker behaves differently
depending on where it is clicked.

### proposed fix

- Show the name being replaced: on focus, set `hint_text` to the remembered value before
  clearing `value`, and clear `hint_text` again on blur. The name stays on screen in grey
  until something else is chosen.
- Decide the restore on what was typed since this focus, not on `text`: track it through
  `on_text_change` (set when the field reports non-empty text, reset on focus). On blur
  with no selection and nothing typed since focus, put the remembered value back.
- Keep `chosen_value()` as it is.
- Update the "Dropdowns for lists nobody wants to scroll" section of `docs/desktop.md`.

Done when clicking a picker and leaving it without typing always shows the same name as
before, the name is visible as a hint while the field is empty, and a test covers a field
whose `text` still holds an earlier value.

### related tickets

- (BLOCKS) [082-F5_inline_transcript_editor](082-F5_inline_transcript_editor.md): the new editor's speaker picker follows the same rule (hint, not a blank field), though it builds its own picker
- (RELATED) [056-P5_editor_windowing](056-P5_editor_windowing.md): PR #92 found the arrow click that does not focus
