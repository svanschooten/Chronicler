# 056-P5_editor_windowing

## The transcript editor builds every row up front

### info

| | |
| --- | --- |
| importance | low |
| danger level | Medium on long sessions: possibly slow editing. Change risk: medium. |
| reach | Editing long transcripts |
| effort | M |
| evidence | Python side measured; client side measured in the desktop client |
| touches | `chronicler/desktop/views/transcript/editor.py`, `chronicler/desktop/views/transcript/view.py`, `chronicler/i18n/` |

### description

The example transcript builds 18,546 control objects in 0.41 s on the Python side, with
only 6 speakers, because each of the 1,686 rows carries every speaker as dropdown options.
The registry's workspace-wide names multiply this. The client-side cost has not been
measured.

### proposed fix

Measure first in the real app with a long transcript. If it is slow, show a window of rows
with paging or jump-to, and build each speaker dropdown's options only when it gets focus.

Done when opening edit mode on the example feels immediate, or the measurement shows no
work is needed.

### outcome

Measured in the desktop client (Xvfb, software rendering): opening edit mode on the
example took about 1.6 s. The editor now builds a window of `WINDOW_SIZE` (100) rows,
about 1,100 controls, and opens in about 0.45 s.

- A pager above the list and again at its end moves a window at a time or jumps to the
  first or last. Its label gives the line numbers and, when timings are real, the
  window's time span.
- With the reader's find showing, edit mode opens a window starting at the first match.
  Without one, it reopens the window it was left on.
- Building speaker options on focus was dropped: in Flet 0.86 clicking a dropdown's arrow
  opens the menu without focusing it, so `on_focus` never fires. Every row still carries
  every speaker, so `chronicler/desktop/widgets.py` is untouched.
- Text still unsaved in the window is saved before its rows are replaced (paging, the
  reload after a delete, finishing editing): the Flet client sends no blur for a focused
  field it takes off the screen. A failed save is undone only once the line's last
  running save ends, so it never takes back an edit that a later save has stored.

Left open: the window caps the rows, not the options. A workspace with many speaker
names still builds 100 x names options per window; only the example's 6 were measured.

See `docs/transcript-editing.md`.

### related tickets

- none
