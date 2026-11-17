# Transcript editing

`chronicler/desktop/views/transcript/editor.py`, `TranscriptService.update_line` /
`delete_line`, `SQLiteTranscriptRepository.update_line` / `delete_line`

Everything around the transcript got rich before the transcript itself did: you could
normalise, transcribe, clean, summarise, export and record, and you could not fix a
misheard word. The text field was `read_only=True` and `update_line` was a stub that
returned its argument and wrote nothing.

## Two modes, not one editable blob

The read view is a single selectable block of text, which is what makes it readable — and
exactly what cannot be edited line by line. So editing is a mode: the toggle in the
transcript panel's header swaps the block for one row per line. Each row still reads like
the transcript (see "Lines that read like the transcript" below).

Whole-blob editing was the obvious alternative and is worse. Parsing the text back into
lines would have to guess where a speaker turn begins, which line each timing belongs to,
and what a line containing a colon means. One mis-parse would silently rewrite the lines
around the one that was edited. Editing one part of one line at a time means an edit
touches exactly the line it was typed into, and nothing else.

Each row shows the line's start time, its speaker and its text, with a delete button on
the hovered row. The "show timestamps" checkbox is disabled while editing, because rows
always show theirs.

### The block is a Text, not a read-only TextField

It used to be the latter, with `min_lines=12`, `max_lines=16` and a blank line between
turns. Three things followed, all wrong: the field stopped growing at sixteen lines
however tall the window was, so most of the panel was empty on a large screen; anything
past the cap was simply not reachable; and the double newline spread a conversation out
until very little of it was on screen at once.

It is now an `ft.Text(selectable=True)` inside a scrolling `ft.Column(expand=True)`.
Turns are joined with a single newline and the breathing room comes from
`TextStyle(height=1.35)`, which is spacing rather than an empty line. `expand` on the
column is what makes the panel fill its container at any size.

Selectability is the reason it stayed a single control rather than becoming one `Text`
per line, which would have made a drag across three turns select nothing — and that is
the property this whole mode exists for.

The "show timestamps" checkbox still reformats the already-loaded lines in place, with no
round trip: `_transcript_body()` rebuilds the string from `transcript_lines` and nothing
re-fetches.

## The focused reader

The book icon in the header opens the whole transcript as one block, with nothing else
on screen. It was a fixed 760x520 dialog, which on a large monitor is a small island —
the opposite of what a focused reading mode is for. It is now sized from `page.width` and
`page.height`, with a floor so a small window still shows something readable and a
fallback for a window that has not reported its size yet.

The title row carries a full-screen toggle, which drives `page.window.full_screen` and
swaps its own icon. The desktop app, packaged or from source, always has a real window
to resize, so the button is always shown.

## Timings are never touched

`update_line` writes text and speaker only. A corrected word must not shift the line off
the audio it came from — the timings are what SRT export and any future audio-follow
feature depend on, and they are not something a text edit has an opinion about.

Re-timing a line is a different feature and would need to be able to see the audio.

## Saving

A text field saves when it closes (Enter, blur, or opening another part), and only when
the value actually changed — the same rule the
Settings page follows, for the same reason: blur fires on every focus change, and a save
plus a confirmation on each one is noise. The editor keeps the loaded line as the
comparison point and updates it after a successful write, so a second blur on a
twice-edited field does not re-save the first version. A speaker saves only when one is
picked.

A failed save reverts the field to what is still on disk and says why. Leaving the typed
text visible after a failed write is the worse option: it looks saved.

Editing one line does **not** reload the list. Reloading would throw away the caret
position and the scroll position on every edit.

## A window of rows, not all of them

The example transcript has 1,686 lines. Building a form row for each, with every speaker
as an option in every row's dropdown, came to 18,546 controls and about 0.4-0.6 s on the
Python side alone, before any of it was sent to the client and laid out (ticket 056).
Plain-text rows (ticket 082) are seven controls each, but 1,686 of them would still be
about 11,800, so the window stayed.

The editor shows `WINDOW_SIZE` (100) rows at a time. Above the list, a pager steps a
window forward or back, or jumps to the first or last one, and says which lines are on
screen ("Lines 101-200 of 1,686"). The same pager ends the list, so reaching the last line
of a window leads straight on to the next without scrolling back up. A transcript that
fits in one window gets no pager.

When the timings are real, the label also gives the window's time span ("Lines 101-200
of 1,686 · 00:04:10-00:08:19"). The reader shows times, not line numbers, so a time is
what you know a passage by when you come from reading it. Timings that are only line
indices (an import without timestamps) get no span, since it would read as a time.
Deleting a line reloads the same window rather than going back to the first; if the
window no longer exists, because its only line was deleted, it falls back to the last one.
Moving to another window scrolls back to its top.

The view keeps one editor for as long as the chronicle is open, so finishing editing and
starting again, with no find showing, reopens the window you left, not the first one.
Leaving edit mode to read a passage should not mean paging back to where you were.

An edit never relies on a blur when the rows are replaced. The Flet client sends no blur
for a focused field that is taken off the screen, so paging, the reload after a delete,
and finishing editing first close the open part, saving its text. The save goes to the
line itself, not to the row, so it does not matter that the row is gone by then.

The line takes the new text when the save starts, not when it ends, so the row shows the
correction as soon as the field closes, and paging straight back during a save rebuilds
the row with it rather than with the old text. A
failed save is undone only once the field's last running save ends: the line and the
row on screen, which may be a rebuilt one, then get what the database is known to hold,
the last text that saved or what the line held before. A failure that a later edit has
already saved over is reported but takes nothing back.

The reader's find does the searching, and edit mode picks it up: with a find showing,
switching to edit mode opens a window that starts at the first match. It starts at that
line rather than at the usual boundary (line 1,201 for a match on line 1,235) because a
`ListView` can only be scrolled to a row the client has already built, and a row far down
a fresh window has not been, so the top of the window is the one place the line is sure
to be seen. Paging from there moves a whole window at a time, and
"last" still goes to the last whole window. A match that has since been deleted leaves
the window where it was.

With 100 form rows that was about 1,100 controls. Measured in the desktop client on the
example, under software rendering on a virtual display, edit mode showed its rows about
0.45 s after the click, and moving to the next window took about 0.3 s. With plain-text
rows a window is about 700 controls whatever the number of speakers; it has not been
re-measured in the desktop client.

## Lines that read like the transcript

Edit mode used to be a row of form controls per line, which looked like a settings page
rather than the conversation being corrected. Each row is now one `Text` in the reader's
style (`TRANSCRIPT_STYLE` in `views/transcript/style.py`), made of three spans:
`[time] `, `Speaker: ` and the text, wrapping the way the reader wraps. The time is muted
and not clickable. The speaker and the text are spans with their own `on_click`. An empty
line shows a muted "(empty line)" so there is still something to click. Rows sit with no
gap between them.

The row under the mouse is tinted (`ThemeColors.hover`) and shows its delete button. The
button is always in the layout and only faded in, and is sized to one text line, so
neither hovering nor a short line changes a row's height.

Clicking a part swaps only that part for its control (`LineRow.show_text_field`,
`show_speaker_picker`). The open row gets an accent bar on its left: the text field is
borderless and in the reader's style, so without the bar nothing would show that the line
is being edited.

### The text field

A click on the text opens a borderless multi-line `TextField` with the line's text, in the
same style, with `shift_enter`. **Enter** saves and closes. **Shift+Enter** adds a
newline. **Esc** discards the edit and closes. **Blur** saves and closes. While it is open,
its text wraps under the start of the field rather than under the time.

The field has `autofocus` and is also given `focus()`. Checked in the Flet web client:
`focus()` alone, called right after the row's update, did not focus the new field, so
typing went nowhere. `autofocus` on the freshly built field did.

### The speaker picker

A click on the speaker opens an editable `Dropdown` with every workspace name, built for
this picker only, so a window of rows builds no options at all. It opens **empty, with
the line's speaker as its hint**, so typing filters at once and the speaker never looks
deleted. Clicking the field opens the menu without losing focus; typing filters it; Enter
picks the highlighted option.

Only a pick saves. Leaving the picker with something typed closes it and saves nothing: a
half-typed filter such as `Az` must not become a speaker. Leaving it with nothing typed
keeps it open, because a click on the picker's own arrow blurs the field while it opens
the menu, and closing then would make the arrow useless. An empty picker only shows the
current name as its hint, so it cannot look like a change. It closes on the next click on
a line, Esc, a pick, paging or finishing.

### Adding a speaker

A line often needs a speaker who is not in the list yet, such as an NPC the GM voices.
While the typed name matches no known name, case and spacing ignored, an
"Add speaker '{name}'" button shows at the end of the row. Clicking it saves the line with
that name, which joins the workspace registry like any other (see
[speakers.md](speakers.md)), and the next picker offers it without a reload. This button
is the only way a new name is saved from the editor.

It is a button, not an extra option in the picker's menu. That was tried first: changing
a `Dropdown`'s options while it is being typed into resets its field in the Flet client,
and the keystrokes that follow are lost. Only the button is updated as you type.

A blur is acted on only after `PICKER_BLUR_GRACE` (0.3 s). Checked in the web client: a
click on a menu option blurs the field first and delivers the pick a moment later, so
closing at once would take the menu away under the click. The "Add speaker" button
blurs the field the same way, and is caught by the same grace.

### Moving between lines

While a text field is open, **Alt+↓** saves it and opens the next line's text, and
**Alt+↑** the previous line's. The opened row is scrolled into view by its key
(`ListView.scroll_to(scroll_key=...)`), which works because a neighbouring row is always
built. At the first or last line of the window the field just saves and closes: moving to
another window is the pager's job, since it rebuilds every row and moves the scroll
position. The speaker picker does not move.

Tab was the first plan and does not work. Checked in the Flet web client: Tab moves the
focus on, to the row's delete button, before the next field exists, so that field's
`autofocus` does not apply, and `focus()` on it had no effect, even after a delay.
Alt+arrows move no focus: the old field is removed while it has the focus, and the new
field's `autofocus` takes it, as it does after a click. A Tab in a field still leaves it,
which saves it like any other blur.

### One part open at a time

The editor holds at most one open part (`TranscriptEditor.open`). Opening another closes
it first, saving a text field. Closing reads the control's value on the server and starts
the save itself, because the control is being removed and a removed field sends no blur.
`open` is cleared before the swap, and every blur, submit and pick handler checks that its
control is still the open one, so a late blur from a field already closed (by Esc, say)
does nothing.

Esc, Alt+↓ and Alt+↑ go through `page.on_keyboard_event`. The editor installs its handler when edit mode
loads, passes on any key it does not use to the handler that was there before, and puts
that one back when editing finishes.

A name saved from a picker is added to the editor's list, so the next picker offers it
without a reload, in the spelling the chronicle keeps (ticket 083).

## Speakers

The speaker picker offers every name in the workspace, not just this chronicle's — same
source as the transcribe dialog, see [speakers.md](speakers.md). A name saved here is
created if new and joins the workspace registry, so a name learned while correcting a
transcript is offered the next time a track is transcribed. A name that matches an
existing one apart from case or spacing is the existing speaker (ticket 083).

An empty pick saves nothing. A line belonging to nobody is not a state the editor should
be able to produce.

## Deleting

A per-line delete confirms first, quoting the line. Transcript text is the one thing in a
chronicle that cannot be regenerated from something else — a re-transcription produces
different words — so a mis-click that silently drops a line is not an acceptable cost for
one saved click.

The speaker row survives its last line. It still maps an audio source to a name, and
`AudioSource.speaker_id` points at it.

## What this is not

Bulk edits belong to the CLEAN task, which is what removes hallucinated repeats across a
whole transcript at once — see [cleaning.md](cleaning.md). Hand-deleting 232 copies of
"Thank you." is not the intended workflow.

There is no undo. The scope here is correcting what a model misheard, not a document
editor.

## Design

The click-to-edit rows were planned in
[superpowers/specs/2026-11-13-inline-transcript-editor-design.md](superpowers/specs/2026-11-13-inline-transcript-editor-design.md)
(wave 11 of [tickets/README.md](../tickets/README.md)), which also records the approaches
that were not taken.
