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
transcript panel's header swaps the block for one row per line.

Whole-blob editing was the obvious alternative and is worse. Parsing the text back into
lines would have to guess where a speaker turn begins, which line each timing belongs to,
and what a line containing a colon means. One mis-parse would silently rewrite the lines
around the one that was edited. One control per line means an edit touches exactly the
line it was typed into, and nothing else.

Each row carries the line's start time, its speaker, its text, and a delete button. The
"show timestamps" checkbox is disabled while editing, because rows always show theirs.

## Timings are never touched

`update_line` writes text and speaker only. A corrected word must not shift the line off
the audio it came from — the timings are what SRT export and any future audio-follow
feature depend on, and they are not something a text edit has an opinion about.

Re-timing a line is a different feature and would need to be able to see the audio.

## Saving

A field saves on blur, and only when the value actually changed — the same rule the
Settings page follows, for the same reason: blur fires on every focus change, and a save
plus a confirmation on each one is noise. The editor keeps the loaded line as the
comparison point and updates it after a successful write, so a second blur on a
twice-edited field does not re-save the first version.

A failed save reverts the field to what is still on disk and says why. Leaving the typed
text visible after a failed write is the worse option: it looks saved.

Editing one line does **not** reload the list. Reloading would throw away the caret
position and the scroll position on every keystroke-and-tab.

## Speakers

The speaker dropdown offers every name in the workspace, not just this chronicle's — same
source as the transcribe dialog, see [speakers.md](speakers.md). A name typed here is
created if new and joins the workspace registry, so a name learned while correcting a
transcript is offered the next time a track is transcribed.

Clearing the speaker saves nothing. A line belonging to nobody is not a state the editor
should be able to produce.

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
