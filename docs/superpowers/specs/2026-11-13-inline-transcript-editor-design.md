# Inline transcript editor: design

Status: agreed 2026-11-13, revised 2026-11-17 after a review of this plan and of PR #92
(ticket 056). Built by tickets 086 and 082-085 in wave 11 of
[tickets/README.md](../../../tickets/README.md), on top of 056.

## Why

The editor works, but it does not feel like editing a transcript. Every line is a row of
form controls (timestamp, speaker dropdown, bordered text field, delete button), so a
screen of it looks like a settings page. What should be on screen is the conversation,
with each part of a line editable where it is.

Clicking a speaker in today's editor also empties the field. That is
`searchable_dropdown` clearing itself on focus so typing filters the list, and it does not
always put the name back (086). In a form it reads as data loss.

## Goals

- Edit mode reads like the reading view: the same `Speaker: text` lines, in the same text
  style (`TRANSCRIPT_STYLE`), wrapping the same way. The only differences are the hover
  tint and the timestamp.
- It is obvious what can be clicked: the row tints on hover, and the speaker and the text
  show a click cursor.
- Clicking the text edits the text in place. Clicking the speaker opens a speaker picker in
  place. Nothing else on the row changes when either opens.
- Clicking a speaker never makes the line's speaker look gone: the current name stays on
  screen until another one is chosen.
- A speaker who is not in the list (an NPC the GM is voicing, say) can be typed in and
  added from that picker, and doing so is easy to discover.
- No row builds a dropdown or a text field until it is clicked.

## Non-goals

- **One view for reading and editing.** Edit mode stays a separate view behind the
  existing toggle. It should read like the reader, but the reader keeps the jobs it is
  tuned for, including selecting text across lines.
- **A character or NPC model.** An NPC is an ordinary speaker. It joins the workspace
  registry like any other name, so it is offered in other chronicles' pickers too. That
  is accepted. A line's `source_id` still records which track, and so which person, it
  came from.
- Editing timings, merging or splitting lines, undo, and bulk relabelling.
- **Removing the window of rows.** 056 (PR #92) shows 100 rows at a time. Plain-text
  rows are cheaper, but 1,686 of them are still about 11,800 controls, so the window
  stays. Whether it can grow is measured after 082, not assumed.

## Anti-goals

- An edit touching anything but the line and the part that was clicked.
- Losing typed text without warning: a failed save reverts the line *and* says so.
- Losing typed text silently because a control was removed before its blur arrived.
- Reloading the list after a single-line save, which loses the scroll position.

## Approaches considered

| | Approach | Trade-off | Outcome |
| - | -------- | --------- | ------- |
| A | Click-to-edit rows inside the existing edit mode, on top of 056's window | Smallest change that fixes the look, keeps the reading view untouched, and reuses 056's save handling | **Chosen** |
| B | One view: rows always shown, wrapped in `SelectionArea` and editable on click, with no toggle | Nicer to use, but a click-drag to select text and a click to edit compete for the same mouse gesture, so it needs a prototype first | Not now: it can be tried later on top of A |
| C | Keep the form rows, restyled to look flatter | Cheap, but every row still builds a dropdown and a text field, and it still behaves like a form | Rejected |

## What 082 takes from 056 (PR #92)

PR #92 was built for the form rows, but most of it is about lines, windows and saves rather
than about how a row looks, and 082 needs all of that. Merge 056 first and build 082 on it.

| From #92 | Under 082 |
| -------- | --------- |
| Window of `WINDOW_SIZE` rows, pager above and below, "Lines 101-200 of 1,686 · 00:04:10-00:08:19", `format_count` | **Kept** as is |
| Edit mode opens on the reader's first find match, and reopens the window it was left on | **Kept** as is |
| Delete reloads the same window, or the last one if that window is gone | **Kept** as is |
| Finding: the Flet client sends **no blur** for a focused field that is taken off the screen | **Kept, and now central.** Closing a control removes it, so closing saves explicitly and never waits for a blur (see "Opening and closing") |
| `save_unsaved()` before paging, reloading after a delete, and leaving edit mode | **Kept, made smaller.** One control is open at most, so it becomes "close the open control, saving it", not a scan of every row |
| A line takes the new value when its save starts; a failure is undone only when that field's last running save ends (`_Saves`, `_settle`) | **Kept.** `_settle` now repaints the row's plain text, or the open control if that part has been reopened |
| `transcript.line_save_failed` names the line by its time | **Kept.** The control is usually closed by the time a save fails |
| A typed speaker name joins the editor's list for later rows | **Kept** |
| Finding: clicking the arrow of an untouched editable `Dropdown` opens the menu without focusing it, so `on_focus` never fires | **Kept as a constraint.** 082 builds the picker on a click on the speaker text and focuses it with `focus()`, so nothing depends on `on_focus` |
| Every row carries every speaker as dropdown options | **Dropped.** Rows have no dropdown; options are built for the one picker that is open |
| `_shown_control()` finds a field by scanning rows for `data` | **Replaced** by a map from line id to its row |
| Tests | **Kept** where they test windows, pager, find, delete and save ordering. Tests that type into a row's always-present `TextField` are rewritten to open the part first |

## The design

### A row

```
[00:12:04] GM: and welcome back boys to another episode of the…            🗑
[00:12:09] Azura: Hello, can you swap the difference? It goes on and wraps
under the speaker, the way it does in the reader.
           ▲ click → speaker picker   ▲ click → text field
```

- One `ft.Text` with `TRANSCRIPT_STYLE`, made of three `TextSpan`s: the timestamp
  (monospace, muted, not clickable), `Speaker: ` and the text. The speaker and text spans
  have `on_click`. A missing speaker shows `common.unknown`, as in the reader.
- The timestamp is always shown in edit mode. The reader's timestamp checkbox stays
  disabled while editing, as it is today. The timestamp is the one difference from the
  reader, because it is what a line is known by in the pager and in a failed-save message.
- The row is a `Container` with no spacing between rows beyond a 1-2 px vertical padding,
  so the lines sit as close as the reader's. `ListView(spacing=0)`.
- Hover: `Container.on_hover` sets a light tint (a new `ThemeColors.hover` for light and
  dark). Spans show a click cursor of their own.
- The delete button sits at the row's end with `visible=False`, shown on the hovered row
  and on the row with an open control. Its confirmation quotes the line, as it does today.
- The speaker is shown on every line. Grouping consecutive lines by speaker is left out on
  purpose: it would hide which line a speaker change applies to.
- Each row has `key=<line id>`, so `ListView.scroll_to(scroll_key=...)` can reach it (085).

A row is seven controls (Container, Row, Text, three spans, delete button) whatever the
number of speakers, against eleven today with six speakers and one more per extra speaker.
The editor keeps a `dict[str, ft.Container]` from line id to row.

### Editing the text

- A click on the text span replaces the row's `Text` with a `Row`: a `Text` holding the
  timestamp and `Speaker: ` spans, then a borderless multi-line `TextField` with the
  line's text, `TRANSCRIPT_STYLE`, `content_padding=0`, `dense=True`, `shift_enter=True`
  and `expand=True`. The field must not move the words around it.
- The field has `autofocus` and is also given `focus()`. In the Flet web client,
  `focus()` alone, right after the row's update, did not focus the new field; `autofocus`
  on the freshly built field did. (This reverses the first draft of this design.)
- **Enter** (`on_submit`) saves and closes. **Shift+Enter** adds a newline.
  **Esc** discards the edit and closes. **Blur** saves and closes, when it arrives.
- It saves only when the text actually changed, through 056's `_start_save`.

### Editing the speaker

- A click on the speaker span replaces it with an editable `Dropdown` (width about 180,
  borderless, dense) followed by a `Text` holding the rest of the line, so the text keeps
  its place.
- **The picker opens empty, with the current name as `hint_text`.** Typing filters at once
  and nothing has to be deleted first, but the line's speaker stays visible in grey until
  something else is chosen. This replaces `searchable_dropdown`'s clear-on-focus for the
  editor. The editor builds its own picker with the same `menu_height` cap; it does not use
  `searchable_dropdown`'s focus and blur handlers.
- Its options come from the `speaker_suggestions` list fetched once per load, built now
  and only for this picker. A name saved from the editor joins that list.
- **Picking an option** (`on_select`, by click or Enter on the highlighted option) saves
  it and closes the picker.
- **Leaving without picking** saves nothing, *even if a name was typed*. A half-typed
  filter such as `Az` must never become a speaker. The way to use a new name is the
  explicit "Add speaker" button (084; a menu option was tried first and reset the field
  on every keystroke). Esc and opening another part close the picker. A
  blur closes it only when something was typed, and only after a 0.3 s grace: in the web
  client a click on a menu option blurs the field before the pick arrives, and a click on
  the picker's own arrow blurs it while opening the menu. An empty picker left open shows
  only the current name as its hint, so it cannot look like a change.
- A name that matches an existing one apart from case or spacing is saved with the
  existing spelling (083, enforced in the repository so every caller gets it).

### Opening and closing

The editor holds at most one open part: `(line id, "text" | "speaker", control)`.

- **Opening** a part first closes the open one (saving a text field), then swaps the
  control in, updates the row, and calls `focus()`.
- **Closing** reads the control's current value on the server side, decides whether to
  save, puts the plain `Text` back, and only then starts the save. It never waits for the
  blur: the control is being removed, and Flet sends no blur for a removed field (056).
- **Esc** sets the open part to nothing *before* the swap, so a blur arriving afterwards
  for that control finds it is no longer the open one and does nothing.
- **Every blur and submit handler checks** that `e.control` is the open control. A stale
  event from a control already closed is ignored. This is also what stops a save from
  happening twice.
- **Paging, the reload after a delete, and leaving edit mode** call `close_open(save=True)`
  first. This is 056's `save_unsaved()`, reduced to the one control that can be open.
- A save that fails after its control has closed is undone by `_settle`, which now
  repaints the row's `Text` spans (or the open control, if that part has been reopened
  since) and shows `transcript.line_save_failed`.

### Esc

Esc goes through `page.on_keyboard_event`. The editor installs its handler when edit mode
opens and removes it when edit mode closes. The handler does nothing unless a part is
open, so Esc elsewhere on the page keeps its meaning.

### Keyboard (085)

While a text field is open, **Tab** and **Shift+Tab** save it and open the next or
previous line's text. The newly opened row is brought into view with
`line_list.scroll_to(scroll_key=<line id>)`. That only reaches rows the client has built,
which the next and previous row are. At the first or last line of the window the field
closes and the pager takes over. If Flet does not let the field handle Tab, **Alt+↓** and
**Alt+↑** are used instead.

## Constraints

- Flet 0.86.5. Checked in the installed package: `Container.on_hover`, `TextSpan.on_click`,
  `Text.spans`, `TextField.shift_enter` / `on_submit` / `focus()`, `Dropdown.hint_text` /
  `focus()`, `ListView.scroll_to(scroll_key=...)`, `Control.key`.
- Checked in the Flet web client (0.86.5, under Playwright) and recorded in
  `docs/transcript-editing.md`: a span click reaches its handler, Enter submits the text
  field and Shift+Enter adds a newline, Esc reaches the page handler with a field focused,
  Enter in the picker picks the highlighted option, and the blur-before-pick order above.
  The row has no click handler of its own, so a span click cannot also click the row.
  Still by hand in the desktop client: the click cursor over spans.
- Thin-client mode: no new RPC methods. `update_line`, `delete_line` and
  `speaker_suggestions` are already exposed.
- Every new string goes in all three message maps (en, nl, de), as `docs/i18n.md`
  requires.
- Views are tested as control trees (`docs/testing.md`). Simulate span clicks, check which
  control replaces the text, and call the open control's handlers directly. Hover and
  focus are checked by hand until 058 exists.

## Left to the builder

- Exact hover tint and padding, within `ThemeColors`. (Built: `ThemeColors.hover`, a
  2 px accent bar on the open row, and a delete button sized to one text line so short
  rows are not taller than long ones.)
- How the open control is swapped into the row. (Built: `LineRow` replaces its body.)

## Ticket order

086 (the shared dropdown, independent, can go now) and 056 (PR #92) → 083 (service) →
082 (the editor) → 084 (new speakers) → 085 (keyboard).

082 is still listed after 036 and 041 because they rewrite the same desktop files. That is
a scheduling choice, not a dependency: if the editor matters more than wave 10, take 082
right after 056 and let 036 and 041 rebase onto it.
