# 085-F7_editor_keyboard_flow

## Correcting a run of lines needs the mouse for every line

### info

| | |
| --- | --- |
| importance | low |
| danger level | None: slower correction. Change risk: low. |
| reach | Everyone who corrects a transcript, in all modes |
| effort | S |
| evidence | inferred |
| touches | `chronicler/desktop/views/transcript/editor.py`, `tests/chronicler/desktop/views/transcript/test_editor.py`, `docs/transcript-editing.md` |

### description

The usual correction pass goes down the transcript, fixing a misheard word here and there.
With click-to-edit (082), each line needs its own click, and nothing on the keyboard moves
on to the next one.

### proposed fix

While a line's text field is open, **Tab** saves it and opens the next line's text, and
**Shift+Tab** does the same for the previous line. The list scrolls so the opened line is
visible. At the first or last line, the field just closes. Speaker editing stays
mouse-first.

Check that Flet 0.86 lets the text field handle Tab instead of moving focus. If it does
not, use **Alt+↓** and **Alt+↑** through `page.on_keyboard_event` instead, and record why
in `docs/transcript-editing.md`.

### related tickets

- (BLOCKER) [082-F5_inline_transcript_editor](082-F5_inline_transcript_editor.md)
