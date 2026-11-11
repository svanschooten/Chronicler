# Search

Two questions, answered by different databases:

| Question | Answered by | Code |
| -------- | ----------- | ---- |
| Which chronicles have this in their title, description or tags? | the workspace database, with `LIKE` | `ChronicleService.search_chronicles` |
| Where was this said? | each chronicle's own `project.db`, with FTS5 | `TranscriptService.search_transcript`, `search_transcripts` |

## The index in each chronicle

Project migration `c5e8a1f3d920` adds `transcript_search`, an FTS5 table with external
content: it indexes `transcript_lines.text` without storing a second copy of it. Three
triggers keep it in sync on insert, delete, and update of `text`, and the migration
rebuilds it from the lines already there, so a chronicle recorded before search existed
is searchable the first time this version opens it.

The tokenizer is `unicode61 remove_diacritics 2`: case is folded in every script, and
"cafe" finds "café" (and the other way round).

**The index is keyed on rowid.** `transcript_lines` has a text primary key, so its rowid
is SQLite's implicit one, which SQLite's documentation says `VACUUM` may renumber. In
practice the copy keeps them (SQLite copies the table whole), and a test snapshots a
chronicle with deleted lines and runs FTS5's `integrity-check` on the copy to keep it so.
Anything that rebuilds the table another way, or puts a file back in place of the live
one (ticket 065's restore), should still finish with the `rebuild` below: it costs
moments, and a stale index finds the wrong lines rather than failing.

**A migration that rebuilds `transcript_lines`** (anything using `batch_alter_table` on
it) copies the table into a new one and drops the old, triggers included, and the copy's
rowids need not match the index. Such a migration must recreate the three triggers and
finish with `INSERT INTO transcript_search(transcript_search) VALUES ('rebuild')`. The
triggers live in the migration file to copy from. Only adding a nullable column is safe
without this, and that is what the 074 rule asks for anyway. See
[storage.md](storage.md#opening-a-chronicle-upgrades-it).

## What a query matches

`SQLiteTranscriptRepository.search` turns the typed text into an FTS5 query with
`fts_query` (`chronicler/core/sqlite/patterns.py`):

- **Every word must appear** in the line, in any order and not necessarily adjacent. So
  "discuss the budget" finds "We should discuss the budget" and "budget: let's discuss
  it".
- **The last word is a prefix**, so results appear while it is still being typed: "bud"
  finds "budget".
- **Each word is quoted.** Nothing typed is read as FTS5 syntax: `AND`, `NEAR(`, a column
  filter or an unbalanced quote are just words. Text with no words searches nothing.

Matching lines come back in transcript order, capped at 200 (`FIND_LIMIT`). A caller may
ask for one more than that, and no further, to tell whether there are more: the find in
the transcript panel does, and says "Showing the first 200 matching lines" when there are.

## Across the workspace: a fan-out

`search_transcripts` opens each chronicle in turn, eight at a time, and asks its own
index. There is no workspace-level index to keep in sync with hundreds of project
databases, some of them linked from elsewhere and edited by other copies of Chronicler.

This is affordable because of ticket 031: with `NullPool` a project database costs about
2 ms to open, so a few hundred chronicles take around a second. The first open of a
chronicle in a process costs more, up to about 44 ms, because it runs its migrations.

Each chronicle found carries its first three matching lines, and `has_more` when there
are others; the chronicle's own find shows them, up to its cap of 200. A chronicle that cannot be opened
is skipped and logged, not an error: a linked file that moved, or one a newer Chronicler
upgraded.

**Searching never upgrades a linked chronicle.** Opening a chronicle migrates it to this
version's schema (the 074 rule), and a linked `project.db` may be shared with someone on an
older Chronicler, who could not open it afterwards. So before opening a linked chronicle
this process has not opened yet, search reads its stamped revision read-only
(`DatabaseManager.would_upgrade_linked`), and skips it if opening would migrate it. It is
searched once someone opens it. The workspace's own chronicles belong to this workspace
alone, so search still upgrades and searches them. See
[storage.md](storage.md#opening-a-chronicle-upgrades-it).

## In the desktop

**The archive search box** shows the chronicles found by title, description or tags
first, and then, under *Said in*, those found by what was said, each with its matching
lines. A chronicle already listed by its title is not listed again there. The transcript
search starts once typing pauses for 0.3 seconds, so typing a word does not open every
chronicle once per letter. A result that arrives after the query has changed is dropped.

When a task finishes, the list is read again with the search kept. The transcript search
then waits two seconds, so tasks finishing one after another start one search between
them, and the *Said in* section already shown stays on screen until the new one replaces
it.

**Find in transcript**, in a chronicle's transcript panel, shows only the matching lines
with a count, through that chronicle's index. Past 200 it shows the first 200 and says
so, rather than a count that looks complete. Clearing the field shows the whole
transcript again, and reloading after an edit keeps the find applied.

Both work the same on a thin client: the server searches, and the results are typed
(`TranscriptMatch`, `TranscriptLine`) over RPC.

## Not done

Results arrive all at once, after the slowest chronicle, rather than one chronicle at a
time: a streamed response would need a different RPC shape. Speaker search, ranking and
semantic search are not built.
