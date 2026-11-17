# 056-P5_editor_windowing

## The transcript editor builds every row up front

### info

| | |
| --- | --- |
| importance | low |
| danger level | Medium on long sessions: possibly slow editing. Change risk: medium. |
| reach | Editing long transcripts |
| effort | M |
| evidence | Python side measured; client side not measured |
| touches | `chronicler/desktop/views/transcript/editor.py`, `chronicler/desktop/widgets.py` |

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

### related tickets

- (BLOCKS) [082-F5_inline_transcript_editor](082-F5_inline_transcript_editor.md): built on this ticket's window, pager and save handling (PR #92). Rows become plain text and speaker options are built only for the picker that is open, which removes the per-row option lists this ticket left in place
- (RELATED) [086-L19_dropdown_clears_on_click](086-L19_dropdown_clears_on_click.md): uses this ticket's finding that a click on a dropdown's arrow does not focus it
