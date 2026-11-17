# 084-F6_new_speaker_in_editor

## Adding a new speaker from the editor works but cannot be discovered

### info

| | |
| --- | --- |
| importance | low |
| danger level | None: a feature that exists but that nobody can find. Change risk: low. |
| reach | Everyone who corrects speakers, most of all a GM voicing NPCs |
| effort | S |
| evidence | read in code |
| touches | `chronicler/desktop/views/transcript/editor.py`, `chronicler/desktop/widgets.py`, `chronicler/i18n/messages/*.py`, `tests/chronicler/desktop/views/transcript/test_editor.py`, `docs/transcript-editing.md` |

### description

A line often needs a speaker who is not in the list. In a D&D session, the GM voices
NPCs, and those lines should be labelled with the NPC's name. The editor already supports
this: a name typed into the speaker dropdown is created if new and added to the workspace
registry (`TranscriptService.update_line`). Nothing on screen says so, though. When the
filter matches nothing, the menu is just empty, which reads as "not possible".

It was decided not to model characters separately from the people who voice them. An NPC
is an ordinary speaker, and its name joins the workspace registry like any other. A line
keeps its `source_id`, so which track, and so which person, it came from is still known.

### proposed fix

In the speaker picker that 082 opens: when the typed text matches no suggestion under
the registry's normalisation, show one option, "Add speaker '{name}'". Picking it, or
pressing Enter while it is highlighted, saves the line with that name. When the typed
text matches a suggestion apart from case or spacing, save the existing spelling (083
does this at the service level as well).

The picker learns what is typed through `Dropdown.on_text_change`. On each change, the
editor replaces one extra option at the end of the list (key: the typed name, text: the
"Add speaker" label) or removes it when the text matches a suggestion or is empty. With
`enable_filter` the add option must still pass the filter, so its text has to contain the
typed name. Check by hand that rebuilding `options` while the menu is open keeps the
menu open and the caret in place. If it does not, show the add option as a button next
to the picker instead, and record why in `docs/transcript-editing.md`.

This option is the only way a new name is saved. Leaving the picker without picking saves
nothing, even with a name typed (082), because a half-typed filter must not become a
speaker.

Done when typing a name that does not exist shows the add option, choosing it labels the
line, and the new name is offered on the next line's speaker picker without reopening edit
mode.

### related tickets

- (BLOCKER) [082-F5_inline_transcript_editor](082-F5_inline_transcript_editor.md)
- (BLOCKER) [083-L18_speaker_case_duplicates](083-L18_speaker_case_duplicates.md)

### outcome

Built as the fallback: an "Add speaker '{name}'" button at the end of the row, updated as
you type. Adding the option to the menu, as proposed, reset the picker's field in the
Flet client on every keystroke (checked in the web client under Playwright), so the
button is the only path. Enter does not add a new name: an editable `Dropdown` has no
submit event when no option is highlighted.
