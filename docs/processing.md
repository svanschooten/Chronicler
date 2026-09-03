# Processing

`chronicler/core/processing/`

Three task handlers today: `IMPORT`, `CLEAN`, `TRANSCRIBE`. Each follows the same
shape — look up the chronicle, open a session against its project database, rewrite
transcript lines inside one transaction, then backfill whatever chronicle metadata the
operation just made stale. That shape lives in `HandlerBase`, so each handler module
contains only what makes it different.

`WorkerHandlers` composes the three handler classes by inheritance rather than
delegation, so they keep sharing a single `db_manager`/`chronicle_repo` pair — and
therefore one archive session — with no forwarding boilerplate. The three classes are
independent: they define disjoint `handle_*` methods and share only `HandlerBase`.

`chronicle_repo` is optional. Without it a handler still rewrites the transcript
correctly; it just cannot tag the chronicle or backfill derived metadata. Tests that
only care about transcript contents leave it out.

## Timestamps

This is the single most load-bearing distinction in the processing code.

| Source | `start_time` / `end_time` |
| ------ | ------------------------- |
| Transcribed audio | Real seconds from the model |
| Timestamped text import | Real seconds, parsed from the cue |
| Plain text import | Synthetic per-line indices |

`get_lines()` orders by `start_time`. Leaving every line at `0.0` made that order an
accident of however SQLite happened to break the tie, rather than a guarantee.
Sequential indices make parse order the persisted order, and give append mode a
meaningful offset to build on.

Because text imports have synthetic times, **duration is only ever backfilled by the
transcribe handler**. Computing it from index-based times would produce a meaningless
value.

## Importing

`RegexImporter` matches line by line. A line that does not match is treated as a
continuation of the current speaker's turn.

Continuation lines are joined with `"\n"`, not `" "`. The source's own line breaks
within one turn are meaningful structure — `export_plaintext` prints each as its own
indented line rather than flattening the turn into one wrapped paragraph. Cleaning
normalises all whitespace including these when it merges consecutive same-speaker
turns, so this does not change cleaned output.

When only a start time is captured per cue, each line's `end_time` is derived from the
*next* line's `start_time`. The last line is left zero-length, its end equal to its own
start, since there is nothing to derive it from.

`start_offset` is a parse-time input rather than something the caller shifts onto the
returned lines afterwards, so every line is built with its final timing.

### Append versus overwrite

Append keeps existing lines and parses the new ones onto the end. The offset has to be
read from the database *before* parsing, because `RegexImporter` lays a file out from
whatever `start_offset` it is given.

The importer is built before the session opens: an unsafe regex is rejected by the
constructor, and an import that cannot run should not bring a project database into
existence on its way to failing.

The final speaker count is the union of the names already present and the names in the
new file. Using `len(speaker_map)` alone would count only the new file's speakers,
undercounting a chronicle that already had others.

## Cleaning

Unlike the import handler, the clean handler does **not** call `attach_speakers`. Those
lines came out of this same database, so they already carry the `speaker_id` of a row
that `delete_all_lines()` leaves in place. Resolving each name back to that same id
would be a query per speaker to learn what the lines already say.

Cleaning only ever merges or drops lines from one existing transcript, so the names on
the cleaned lines cover the whole thing — no need to re-read every line back the way an
append-capable import does.

## Transcription

`faster-whisper` does not diarize, so every segment in one file belongs to the same
speaker. `speaker_name` says which. One audio source is one participant's own track and
the caller already knows whose, so this is what makes output correctly attributed
rather than generically labelled.

Timestamps are used **as-is, never offset** — the opposite of import's append mode. Each
audio source is one participant's track from the same recording session, already
time-aligned with every other track, so the raw per-segment seconds are real positions
on a shared timeline and sorting the combined transcript by `start_time` interleaves
speakers correctly for free.

Re-transcribing replaces only *that speaker's* lines, via
`delete_lines_by_speaker`, so another participant's already-transcribed track survives.
The speaker is resolved from the task payload rather than from the transcribed lines,
because the replacement has to happen even when the track turned out to be silent.

`status` is set to `Transcribed` only if it is still the untouched `Imported` default,
so a chronicle whose status was already something else on purpose does not get stomped
back.

### Model loading

`WhisperModel` is constructed only inside `_get_model()`, called only from
`transcribe_audio()`, called only when a `TRANSCRIBE` task actually runs. Nothing at
import or startup time touches it, so the model downloads on first real transcription
rather than on every app launch. Loaded models are cached by size so a second task does
not reload.

`faster_whisper` is imported lazily inside the function. Importing `transcriber.py`
must not require the optional `transcription` extra to be installed, and must never
trigger a download just by being imported.

`transcribe_audio` is synchronous and CPU-bound — a long recording can take minutes — so
callers on an event loop must run it via `asyncio.to_thread()`. In desktop full-stack
mode that loop is shared with the UI itself.

A missing extra raises a clear `RuntimeError` naming the `pip install`, rather than
crashing the worker loop.

## Transactions

Repository methods do not commit internally. Each handler commits once at the end and
rolls back on any exception, so a crash partway through leaves the previous transcript
untouched rather than half-deleted.

## Formatting

`chronicler/core/formatting.py` is shared by chronicle duration display, the transcript
view's timestamp toggle, timestamped export and timestamped import, so a timestamp
reads the same everywhere instead of each call site inventing its own convention.

* `format_duration` — "1h 24m", "45m 12s", "12s". Not zero-padded; it is a summary, not
  a clock.
* `format_timestamp` — fixed-width `HH:MM:SS`, always zero-padded so a column lines up.
* `parse_timestamp` — the inverse, also accepting `MM:SS` and a fractional-seconds
  suffix, since that is a common way for a hand-edited or tool-exported transcript to
  write a timestamp. Raises `ValueError` on anything else: a malformed timestamp in an
  import file should fail loudly, not silently become `0:00`.
