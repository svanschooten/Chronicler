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
**Shift+Tab** does the same for the previous line. Speaker editing stays mouse-first.

- Bring the opened row into view with `line_list.scroll_to(scroll_key=<line id>)`. 082
  gives every row `key=<line id>`. `scroll_to` only reaches rows the client has built,
  which a neighbouring row always is, so this is enough for one step. It is not enough to
  jump to an arbitrary line, which is why 056 opens a window starting at a found line
  instead.
- At the first or last line of the window, the field saves and closes, and the pager
  takes over. Tab does not page on its own: a page change rebuilds every row and moves the
  scroll position, which should be the user's choice.
- The save goes through 082's close-and-save, so the next field opens only after the
  current one has been swapped back to text.

Check that Flet 0.86 lets the text field handle Tab instead of moving focus. If it does
not, use **Alt+↓** and **Alt+↑** through the editor's `page.on_keyboard_event` handler
instead, and record why in `docs/transcript-editing.md`.

### related tickets

- (BLOCKER) [082-F5_inline_transcript_editor](082-F5_inline_transcript_editor.md)

### outcome

Built with the fallback keys, **Alt+↓** and **Alt+↑**. Tab does not work in Flet 0.86
(checked in the web client under Playwright): it moves the focus to the row's delete
button before the next field is built, so that field's `autofocus` does not apply, and
`TextField.focus()` had no effect even after a 0.4 s delay. Recorded in
`docs/transcript-editing.md`.
