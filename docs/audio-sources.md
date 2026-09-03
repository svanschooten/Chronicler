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

## Where a chronicle's audio lives

`DatabaseManager.sources_path_for(chronicle_id, project_path)` is the single answer:

* **normal chronicle** — `<workspace>/chronicles/<id>/sources/`
* **linked chronicle** — `sources/` beside its `project.db`, wherever the user put it

A linked chronicle's files were never in the workspace, so looking there made every one
of its sources read as missing while `chronicle_directory()` — used by *Open folder* —
correctly resolved the external path. The two disagreed.

`TranscriptService.sources_dir` and `HandlerBase.sources_root_for` both go through that
one function, which is why they are async: the answer depends on the chronicle row.
`ChronicleService.add_audio_source` uses it too, so an import into a linked chronicle
lands beside its database rather than in a workspace directory nothing reads.
