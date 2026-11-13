# Inline transcript editor: design

Status: agreed 2026-11-13. Built by tickets 082-085 in wave 11 of
[tickets/README.md](../../../tickets/README.md).

## Why

The editor works, but it does not feel like editing a transcript. Every line is a row of
form controls (timestamp, speaker dropdown, bordered text field, delete button), so a
screen of it looks like a settings page. What should be on screen is the conversation,
with each part of a line editable where it is.

## Goals

- Edit mode reads like the transcript: timestamp, speaker and text as plain text, in the
  reading view's font and line height.
- It is obvious what can be clicked: the row tints on hover and the cursor changes.
- Clicking the text edits the text in place. Clicking the speaker opens a speaker picker in
  place.
- A speaker who is not in the list (an NPC the GM is voicing, say) can be typed in and
  added from that picker, and doing so is easy to discover.
- Ticket 056 closes as a side effect: rows are cheap, and dropdown options are built only
  for the speaker being edited.

## Non-goals

- **One view for reading and editing.** Edit mode stays a separate view behind the
  existing toggle. It should be readable, but it is not tuned for reading: the reading
  view keeps that job, including selecting text across lines.
- **A character or NPC model.** An NPC is an ordinary speaker. It joins the workspace
  registry like any other name, so it is offered in other chronicles' pickers too. That
  is accepted. A line's `source_id` still records which track, and so which person, it
  came from.
- Editing timings, merging or splitting lines, undo, and bulk relabelling.

## Anti-goals

- An edit touching anything but the line and the part that was clicked.
- Losing typed text without warning: a failed save reverts the line *and* says so, as it
  does today.
- Reloading the list after a single-line save, which loses the scroll position.

## Approaches considered

| | Approach | Trade-off | Outcome |
| - | -------- | --------- | ------- |
| A | Click-to-edit rows inside the existing edit mode | Smallest change, keeps the reading view untouched, fixes 056 | **Chosen** |
| B | One view: rows always shown, wrapped in `SelectionArea` and editable on click, with no toggle | Nicer to use, but a click-drag to select text and a click to edit compete for the same mouse gesture, so it needs a prototype first | Not now: it can be tried later on top of A |
| C | Keep the form rows, restyled to look flatter | Cheap, but every row still builds a dropdown and a text field, so 056 stays open and it still behaves like a form | Rejected |

## The design

### A row

```
[00:12:04]  GM        and welcome back boys to another episode of the…   🗑
[00:12:09]  Azura     Hello, can you swap the difference?
            ▲ click → speaker picker    ▲ click → text field
```

- A container with three texts: timestamp (monospace, muted, always shown), speaker (fixed
  width so the texts line up, bold) and text (expands and wraps).
- Hover: a light tint from the theme (`ThemeColors`, both light and dark) and a click
  cursor over the speaker and the text. The timestamp is not clickable.
- The delete button shows only on the hovered row or the row being edited. Its
  confirmation quotes the line, as it does today.
- The speaker is shown on every line. Grouping consecutive lines by speaker is left out on
  purpose: it would hide which line a speaker change applies to.

### Editing the text

- A click puts a borderless multi-line `TextField` in place of the text, with `autofocus`,
  `shift_enter=True` and the line's current text.
- **Enter** saves and closes it. **Shift+Enter** adds a newline. **Esc** discards the edit
  and closes it. **Blur** saves, as it does today.
- It saves only when the text actually changed. A failure reverts the line and shows a
  snackbar.

### Editing the speaker

- A click puts `searchable_dropdown` in place of the speaker, with `autofocus`. Its
  options (`speaker_suggestions`) are fetched once per edit-mode load and turned into
  options only now. A name saved from the editor is added to that local list, so the next
  line's picker offers it without a reload.
- Picking or typing a name saves it and closes the picker. Leaving without a change
  closes it with nothing saved.
- A typed name that matches nothing shows an "Add speaker '{name}'" option (084). A
  name that matches an existing one apart from case or spacing is saved with the existing
  spelling (083, enforced in the repository so every caller gets it).
- Clearing the speaker still saves nothing.

### Only one control open at a time

Opening a part closes whatever is open first, and an open text field saves on blur as it
closes. The editor tracks the open line and part, and puts the plain text back on close.

### Keyboard (085)

While a text field is open, **Tab** and **Shift+Tab** save it and open the next or previous
line's text, scrolling it into view. If Flet does not let the field handle Tab,
**Alt+↓** and **Alt+↑** are used instead.

## Constraints

- Flet 0.86.5. Checked in the installed package: `Container.on_hover`,
  `GestureDetector.mouse_cursor`, `TextField.autofocus` / `shift_enter` / `on_submit`,
  `Dropdown.autofocus`. Esc and the fallback keys go through `page.on_keyboard_event`.
- Thin-client mode: no new RPC methods. `update_line`, `delete_line` and
  `speaker_suggestions` are already exposed.
- Every new string goes in all three message maps (en, nl, de), as `docs/i18n.md`
  requires.
- Views are tested as control trees (`docs/testing.md`). Simulate clicks and check which
  control replaces the text. Hover and focus are checked by hand until 058 exists.

## Left to the builder

- Exact hover tint and spacing, within `ThemeColors`.
- Whether clicks come through `Container.on_click` or a `GestureDetector`.
- How the editor tracks and swaps the open control.

## Ticket order

083 (service, independent) → 082 (the editor) → 084 (new speakers) → 085 (keyboard).
082 closes 056. The wave sits after wave 10 because 036 and 041 rewrite the same desktop
files, and 040 and 043 reshape the code 083 touches.
