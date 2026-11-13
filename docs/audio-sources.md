# Audio sources

`audio_sources` table in the project database, `AudioSourceRepository`,
`TranscriptService.list_audio_sources`

A chronicle's audio tracks used to be nothing but files in a directory. There was
nowhere to record that a track had been transcribed, which speaker it belongs to, or
whether it had been normalised — so every one of those had to be asked again each time.

The `audio_sources` table fixes all three at once. It is the spine that resumability,
normalisation state and speaker memory all hang off.

## Who owns the truth

**The filesystem owns existence. The database owns state.**

`list_audio_sources` reconciles the two on every call: it walks
`chronicles/<id>/sources/`, registers anything it has not seen, and returns the rows.
That means a track copied into the directory by hand — the Craig-download workflow, or a
recording bot dropping files in — is picked up with no import step at all.

A row whose file has disappeared is **not deleted**. It comes back with `missing=True`,
keeping its speaker assignment and history, because a file that vanished is usually a
mistake to be corrected rather than an instruction to forget everything about it.

Normalisation outputs (`*.normalized.wav`) are skipped during the walk. They are
derived artifacts, not sources in their own right.

## Content fingerprints

`content_hash` is what makes "skip if already done" honest. Replace a file and its work
re-runs; leave it alone and it does not.

`fingerprint_file` hashes the file's **size plus its first and last 256 KB**, not the
whole file. Whole-file hashing of a multi-hundred-megabyte recording costs seconds of
I/O every time the panel refreshes, and this is not a security boundary — it answers
"did this file change", where a size change or an edit at either end is what actually
happens in practice. A crafted file that collides is possible and harmless.

## Completion is a pair, not a flag

Both `is_transcribed` and `is_normalized` require **two** things: the state is `DONE`
*and* the hash recorded at completion still matches the file on disk.

That distinction is what makes replacing a track behave correctly. After a swap the row
still reads `transcription_state == DONE` — the run genuinely happened, and its error
and timestamp are still worth showing — but `is_transcribed` is `False`, so the work is
offered again.

## States

`SourceState` is `PENDING` → `RUNNING` → `DONE` | `FAILED`, tracked independently for
transcription and normalisation. A track can be normalised but not transcribed, or the
reverse.

A successful run clears the previous error; a failure records it and leaves it visible
in the Sources panel rather than only in the task list.

## Speaker memory

`speaker_id` on the row is what lets the UI stop asking. The first time a track is
transcribed the speaker is prompted for and remembered; afterwards the Sources panel
pre-selects it, and assigning a speaker is its own action, separate from transcribing.

This is the flexible version of the prototype's `voice_mapping` config, which mapped
filename fragments to names and could not cope with a name it had not been told about.

## Lines remember their track

Each transcript line has a `source_id` pointing at the row that produced it. Without it,
re-transcribing could only delete by speaker, so a second track for one speaker (a split
recording, a Discord user who rejoined, a repeat in-app recording) wiped the first.

Re-transcribing a track replaces its lines, hand edits included. The transcribe dialog
says so before a re-run.

A line with no `source_id` is never deleted by a re-run. Imported transcripts have none,
and neither do lines from before this column existed that could not be attributed.

The attribution happens once, in migration `f6c3a9d2b417`: a speaker with exactly one
transcribed track gets that track on all their lines. An earlier version did this on
every re-run instead, and so deleted a speaker's imported lines whenever they also had
one transcribed track.

Two consequences of attributing only when it is certain:

* A legacy chronicle in which one speaker had two transcribed tracks keeps those lines
  untracked. Re-running either track adds its new lines next to the old ones, so the
  chronicle ends up with duplicates to delete by hand.
* A legacy chronicle that mixed imported lines with one transcribed track for the same
  speaker gets the imported lines attributed to that track too. Nothing recorded the
  difference, and the old code deleted them on a re-run anyway.

`MergeSameSpeaker` never joins lines from different tracks, so a merged line can always
be replaced along with the one track it came from.

`start_offset` is seconds added to every timestamp the track produces. It is set in the
transcribe dialog and stored on the row.

## Where a chronicle's audio lives

`DatabaseManager.sources_path_for(chronicle_id, project_path)` is the single answer:

* **normal chronicle** — `<workspace>/chronicles/<id>/sources/`
* **linked chronicle** — `sources/` beside its `project.db`, wherever the user put it

It is a pure lookup and creates nothing; `ensure_sources_path_for` creates the folder and
is used only when audio is added. Reading a chronicle that has no row, or whose linked
`project.db` has moved, raises (`LookupError`, `FileNotFoundError`) rather than creating a
new empty database.

A linked chronicle's files were never in the workspace, so looking there made every one
of its sources read as missing while `chronicle_directory()` — used by *Open folder* on a
full stack — correctly resolved the external path. The two disagreed.

`TranscriptService.sources_dir` and `HandlerBase.sources_root_for` both go through that
one function, which is why they are async: the answer depends on the chronicle row.
`ChronicleService.add_audio_source` uses it too, so an import into a linked chronicle
lands beside its database rather than in a workspace directory nothing reads.

## Which files count

`chronicler/core/audio_files.py` is the one list: `mp3`, `wav`, `m4a`, `m4b`, `mp4`, `flac`,
`ogg`, `opus`, `webm`, `aac`, `aif`, `aiff` and `wma`, in any case. `mp4` and `webm` are
video containers, usually a recorded call; transcription reads their sound track.

* **Listing.** Only files in `sources/` with one of those extensions are tracks. Hidden
  files, `desktop.ini` and normalized copies are ignored, so tracks copied in by hand are
  picked up and stray files are not.
* **Importing.** The file picker offers only those extensions, and
  `ChronicleService.add_audio_source` refuses anything else with `UnsupportedAudioError`,
  deleting the staged file. Without that, a thin client or a renamed file could put a file
  in `sources/` that is never listed and never exported. The desktop import checks the name
  before it stages the file or creates a chronicle, so a refusal leaves nothing behind.
* **Rows from before the rule.** Listing used to register every file. A row for a file that
  is not audio is dropped the next time the tracks are listed, unless it was transcribed:
  its lines name it, so it stays. Whether any row reads as missing depends on whether its
  file is still there, not on its extension.
