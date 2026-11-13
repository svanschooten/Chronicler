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

In the speaker control that 082 opens: when the typed text matches no suggestion under
the registry's normalisation, show one option, "Add speaker '{name}'". Picking it, or
pressing Enter, saves the line with that name. When the typed text matches a suggestion
apart from case or spacing, save the existing spelling (083 does this at the service
level as well).

Done when typing a name that does not exist shows the add option, choosing it labels the
line, and the new name is offered on the next line's speaker picker without reopening edit
mode.

### related tickets

- (BLOCKER) [082-F5_inline_transcript_editor](082-F5_inline_transcript_editor.md)
- (BLOCKER) [083-L18_speaker_case_duplicates](083-L18_speaker_case_duplicates.md)
