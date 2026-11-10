# Storage

`chronicler/core/database_manager.py`, `chronicler/core/database.py`,
`chronicler/core/project_database.py`, `chronicler/core/sqlite/`

Two database schemas, two Alembic migration chains.

## Archive database

One per workspace, at `<workspace>/chronicler.db`. Holds the chronicle index, the task
queue, and tags. Tags are workspace-level rather than owned by a chronicle, which is
why they live here.

## Project database

One per chronicle, at `<workspace>/chronicles/<id>/project.db`, holding the transcript,
speakers, and per-chronicle metadata. This is what makes a Chronicle portable: it can
be copied, archived or shared without the rest of the workspace.

A **linked chronicle** has `project_path` set and keeps its `project.db` wherever the
user put it, outside the workspace. `delete_chronicle` must never remove that directory
— only a chronicle whose data actually lives under `<workspace>/chronicles/<id>/` gets
its directory removed.

## One process per workspace

`chronicler/core/workspace_lock.py`

A workspace belongs to one process at a time. `init_archive` takes an exclusive OS lock
on `<workspace>/.chronicler.lock` (`fcntl.flock` on Linux and macOS, `msvcrt.locking` on
Windows), and `close_all` releases it. A second desktop app or server on the same
workspace gets `WorkspaceLockedError`: the desktop shows it on the startup screen, and
the server exits with status 1 and the message.

The lock call can also fail because the filesystem cannot take a lock at all: some NFS,
SMB and FUSE mounts answer `flock` with `ENOLCK`, `EINVAL` or `EOPNOTSUPP`. That raises
`WorkspaceLockUnavailableError`, reported the same two ways but naming the OS error and
suggesting a local disk. Only "held by someone else" counts as locked: `EWOULDBLOCK`,
`EAGAIN` or `EACCES` from `flock`, and `EACCES` or `EDEADLOCK` from `msvcrt.locking`.

Before locking, the workspace is probed by creating and removing a file in it (`os.access`
ignores ACLs on Windows). A folder that cannot be created or written to raises
`WorkspaceNotWritableError`, reported the same two ways with the OS reason.
`Settings.is_workspace_valid` uses the same probe, and both setup wizards call it to refuse
an existing folder that cannot be written to. A folder that does not exist yet is
accepted there and created at startup.

`init_archive` releases the lock again if anything after taking it fails, including
creating `imports/`. After `close_all` the manager no longer holds the lock, but its
engines would reconnect if used; nothing reuses a closed manager today.

Sharing a workspace between processes would need task leases and heartbeats so a crashed
worker's tasks could be told apart from a live one's. Ruling it out keeps task recovery a
plain reset at startup.

The OS drops the lock when the process ends, however it ends, so a crash or a kill never
leaves a stale lock behind. The lock file itself stays and is harmless.

The lock is local to one machine. Two machines opening a synced copy of one workspace
(Dropbox, OneDrive, a network share) do not see each other's lock, so only open a synced
workspace on one machine at a time.

## Alembic without an `alembic.ini`

`_run_alembic_upgrade` runs one chain against an already-open sync connection, handed
to `env.py` through `config.attributes["connection"]`.

There is no static `alembic.ini` because the project chain runs against a different
`project.db` per chronicle, so there is no single fixed URL to put in a config file.
The already-open connection carries that instead, bridged from the app's async engine
via `AsyncConnection.run_sync()`, which reuses the same connection and transaction
rather than opening a second one.

Both `env.py` files fall back to building a standalone async engine from
`sqlalchemy.url` for CLI use (`alembic revision --autogenerate`, manual
`alembic upgrade head`).

Migration files under `migrations/*/versions/` are excluded from ruff. Alembic's own
`script.py.mako` boilerplate style (`Union`/`Sequence`, unsorted imports) is what every
future autogenerate produces, so excluding beats hand-fixing each one.

## One owner for opening a chronicle's database

`DatabaseManager` alone knows where a chronicle's `project.db` is. Callers pass a
chronicle id, never a path:

- `project_path_for(id)` is the linked path, or `None` for the workspace default. It reads
  the chronicle's row through a short archive session of its own and remembers the answer
  until `close_project`. A caller's open session is never touched, which is what used to
  fail when `TranscriptView.did_mount` started three panel loads on one shared session: a
  session that is still opening its connection refuses a second concurrent operation.
- `transaction(id)` is the way to write. It commits when the block ends and rolls back if
  it raises, so a handler holds no `try / commit / except: rollback` and never calls
  `commit` itself.
- `get_project_session(id)` is for reads. The caller closes it with `async with`.
- Both take `must_exist`, which turns an unknown chronicle into `LookupError` and a linked
  file that has moved into `FileNotFoundError`, instead of silently creating a new empty
  database. Handlers without an archive connection to check against skip it.

The cache is dropped by `close_project`, which runs whenever the cached answer stops being
true: `ChronicleService.update_chronicle` calls it when `project_path` changes, and
`delete_chronicle` after the row is gone.

## Migrations are serialised process-wide

`DatabaseManager` holds one `asyncio.Lock` guarding **every** migration it runs — the
archive chain and every project chain alike.

One lock for all of them, not one per database, because **Alembic drives migrations
through a process-global proxy**. Two chains running concurrently corrupt each other's
`EnvironmentContext` even when they target different files, which surfaces as
`KeyError: 'config'` from Alembic's own teardown.

The lock also closes a check-then-populate race in `_project_engine`: the cache lookup
and the migration are separated by awaits, so concurrent first-time callers all missed
the cache and all ran Alembic against the same file. That surfaced as
`table audio_sources already exists` and `database is locked`.

Both are easy to trigger: `TranscriptView.did_mount` fires three panel loads at once
(transcript, sources, summaries), and each opens a project session.

If a workspace was opened by a build without the lock, a project database can be left
with the new tables created but the Alembic version never stamped, and it will fail on
every subsequent open. Recover by stamping it to the revision whose tables already
exist, or — since the affected tables are new and empty — by deleting that chronicle's
`project.db`, which is rebuilt on next open. The transcript is regenerated from the
sources; only speaker assignments and summaries are lost.

## Sessions

`get_archive_session()` returns a new session each call. Project engines are cached per
chronicle id, because creating one runs the migration chain.

The rule that matters: **the worker holds no session across steps.** `WorkerManager` and
the task handlers take a session factory and open a short session for each group of
repository calls, the way the RPC layer scopes each request. Two things follow:

- Nothing is shared with the UI or HTTP request handling. Those run as separate
  coroutines on the same event loop, and `AsyncSession` does not allow interleaved
  operations on a shared instance.
- A `database is locked` error poisons only the session it happened on. One long-lived
  session would need a rollback nobody issues, and every later poll would fail with
  `PendingRollbackError`.

Progress updates are best effort: a locked write is logged and skipped. A task's final
status write retries for up to `STATUS_WRITE_TIMEOUT` (30 seconds), so a brief lock does
not lose a finished result.

## Journal mode and foreign keys

Both databases run in SQLite's default rollback journal, not WAL, and foreign keys are not
enforced (`PRAGMA foreign_keys` is never turned on).

**Rollback journal.** A writer briefly locks readers out, which is where most `database is
locked` errors come from. The busy timeout (5 seconds), the worker's short sessions and its
retried status writes absorb that (see [Sessions](#sessions)). WAL would let readers and
the writer run together, but it keeps two extra files, `-wal` and `-shm`, beside each
database, and the database is only consistent with all three together. Sync tools such as
Dropbox and OneDrive copy files independently and can ship a `project.db` without its
`-wal`, which loses or corrupts recent writes on the other machine. The README promotes
exactly that kind of storage, so the default journal stays until there is a reason to
trade that safety away. A chronicle that is copied or shared should be copied while
Chronicler is closed either way.

**Foreign keys.** The schemas declare them, but SQLite ignores them unless the pragma is
on for each connection. The code does what cascades would do instead:
`SQLiteChronicleRepository.delete` removes a chronicle's tasks and tag links in the same
transaction, and a transcript line keeps its speaker row because speakers outlive their
lines on purpose. Turning the pragma on now would first need a check that no existing
workspace holds a dangling reference.

## Opening a chronicle upgrades it

The first open of a project database in a process runs its migration chain to head (see
[Migrations are serialised process-wide](#migrations-are-serialised-process-wide)), so the
file moves to the newest schema in place. An older Chronicler cannot open it afterwards:
Alembic stops with `Can't locate revision identified by '…'`.

This matters for anything shared: a chronicle in a synced folder, one sent as a zip, or a
linked `project.db`. Whoever opens it with the newest version decides the version
everyone else needs. Until ticket 074 settles a compatibility rule, keep everyone sharing
chronicles on the same release.

## Deleting a chronicle closes its database first

`ChronicleService.delete_chronicle` calls `DatabaseManager.close_project(id)` before it
touches the filesystem, and that ordering is the whole point of the method.

Project engines use `NullPool`: a connection, and the thread and open file behind it,
lives only as long as the session that took it. Before that, a cached engine kept one
open per chronicle, so a long-running process that opened 50 chronicles held 50 threads
and 50 files (2 threads rose to 52), and deleting a chronicle failed on Windows. Linux
unlinks a file that is still open, but Windows refuses:

```
[WinError 32] The process cannot access the file because it is being used by
another process: '...\chronicles\<id>\project.db'
```

A connection now costs about 2.1 ms to open instead of 0.9 ms from a pool. The engine
stays cached, because the cache also records that a database has been migrated.

`close_project` pops the engine out of the cache, so a project.db recreated at the same
path is migrated again. The ordering in `delete_chronicle` still matters: no session may
be open on the file when it is removed. `remove_directory` keeps its retries, since
virus scanners also hold files briefly.

A **linked** chronicle is closed the same way and its files are then left alone — the
`project.db` belongs to whoever the workspace borrowed it from, and deleting the
chronicle here unlinks it rather than destroying a database that may be shared.

`remove_directory` retries a few times before giving up. Disposing the engine releases
the handle Chronicler owned; on Windows a virus scanner or the search indexer can still
hold one for a moment. The desktop reports a failure that outlasts the retries as a
message rather than letting it reach Flet as an unhandled error.

## Repository notes

* **`get_all()` orders by `created_at DESC`.** Without an `ORDER BY` the archive
  returned whatever order SQLite happened to produce, so the list could reshuffle
  between two refreshes that changed nothing.
* **`delete_chronicle` cleans up by hand.** `DBTask.chronicle_id` and `chronicle_tags`
  have no `ondelete=CASCADE` at the schema level, and SQLite does not enforce foreign
  keys by default here anyway, so orphaned task rows and tag associations are removed
  explicitly in the same transaction as the chronicle row.
* **Chronicle search matches tags through a subquery, not a join**, so a chronicle
  carrying two matching tags is returned once rather than twice. A `DISTINCT` over the
  whole entity would work too, but only accidentally, and would need revisiting the
  moment another to-many relationship joins the search.
* **`delete_all_lines()` deliberately does not touch speakers.** It used to, which meant
  `get_or_create_speaker()` never found an existing speaker after a delete and every
  import or clean assigned fresh speaker ids. Leaving speaker rows in place lets the
  lookup-by-name reuse the same row, and therefore the same id, across re-runs.
* **`get_or_create_speaker` flushes rather than commits**, making the row visible to
  `refresh()` and to later queries in the same transaction without ending it. The
  caller controls the transaction boundary.
* **`TranscriptRepository.search` raises `NotImplementedError`** rather than silently
  returning `None` against a `-> list[...]` annotation. `SearchService` had exactly that
  bug.

## `LIKE` escaping

`chronicler/core/sqlite/patterns.py` escapes `%` and `_` in user input. Someone
searching for `100%` means a title containing `100%`, not "anything containing 100".
Without this a bare `%` matched every row, which reads as the search box being broken.

The escape character is `!` rather than the more usual backslash: SQLite has no default
`LIKE` escape character at all — one must be declared per query via `ESCAPE`, which
SQLAlchemy's `escape=` parameter does — and `!` is rare in transcript titles and tags,
so it appears less often in the escaped output than a backslash would.

## `DBProjectMetadata`

A reserved key/value table for per-chronicle provenance. Nothing reads or writes it
yet. It is kept in sync with the baseline migration that already creates the table
rather than dropped, so the ORM metadata and the on-disk schema do not disagree.

## Linking a project database from elsewhere

`ChronicleService.link_external_chronicle(path)` registers a `project.db` that lives
outside the workspace and then reads what it can out of it: speaker count, duration from
the last line's end time, `Transcribed` status and the `Transcript` tag when there are
lines. An empty database stays `Imported` and claims no duration.

It is one service call, not a create-then-inspect sequence in the client. A thin client
would otherwise make four round trips, and the state it replaces was worse than slow: a
linked chronicle showed "Imported", zero speakers and no duration however full the
database was.

The title comes from the containing directory, falling back to the filename when that
directory is the generic `chronicles`.

Before anything is registered, `check_linkable_project` opens the file read-only and
refuses it with a `LinkRefusedError` when it does not exist, is not a Chronicler project
database (no `alembic_version` table: another app's SQLite file, an empty file, or not
SQLite at all), or carries a revision this version does not know, meaning a newer
Chronicler made it. This check comes first because opening a project runs its migrations,
which would otherwise write Chronicler's tables into whatever file was picked. A file that
passes but then fails while being read is unregistered again and refused as unreadable.
Either way the chronicle count is unchanged, and the error's `reason` lets the desktop say
why in the user's language. A thin client does not offer *Link*: the picker returns a path
on the client's machine, and the server would look for it on its own disk.

`hydrate_from_project` is separate from the link so it can be re-run — the chronicle
view's *Identify speakers* covers the speaker half of the same job.

## Exporting a Chronicle as an archive

`TranscriptService.export_zip(chronicle_id, include_sources=False)` packs one chronicle
into a portable `.zip`, built by `chronicler/core/services/bundle.py`:

```text
<Chronicle title>/
├── chronicle.json     What the project database cannot say about itself
└── project.db         A consistent snapshot
└── sources/           Only when the audio was asked for
```

Everything sits under one folder named after the chronicle, so unpacking it into a busy
directory leaves one directory behind rather than loose files. That folder name is also
what `link_external_chronicle` reads the title from, so an unpacked archive comes back
named correctly even if nothing reads the manifest.

### Off the event loop

`export_zip` runs `format_bundle` through `asyncio.to_thread`. Compressing 200 MB of
audio takes seconds, and the event loop it would otherwise block is the desktop UI's, or
the server's for every client.

`format_bundle` writes the zip straight into the `bytearray` it returns. Writing to a
`BytesIO` and copying it out at the end was one step that held the GIL for long enough
to stall the loop from the worker thread. Because that target cannot seek, each entry's
sizes follow its data (a data descriptor) instead of sitting in its local header. Every
common zip reader handles that.

### Why a manifest

Title, description, kind and tags live in the **workspace** database, not the
chronicle's own — see the storage model above. A `project.db` lifted out on its own
therefore arrives anonymous. `chronicle.json` carries that metadata alongside it, plus
the Chronicler version and the export time.

### Why `VACUUM INTO` rather than copying the file

`DatabaseManager.snapshot_project` asks SQLite to build the copy. The project engine is
cached and may have a connection open, so copying the file could catch a write half-made
— and a torn database is a bundle that looks fine until someone opens it. `VACUUM INTO`
writes a consistent copy from committed pages instead, without disturbing the live
connection, and compacts it on the way out. It refuses to overwrite an existing file,
which `snapshot_project` surfaces as `FileExistsError` rather than silently shipping a
stale snapshot.

### Why the audio is opt-in

A bundle without audio is a few hundred kilobytes; one with it is however many hours of
recording, and in thin-client mode that is a whole HTTP response held in memory on both
ends. Left out, the `audio_sources` rows still exist, so the tracks read as *missing*
rather than as never having been there, and `chronicle.json` lists the filenames that
were omitted. Normalized derivatives (`*.normalized.wav`) are never carried — they are
rebuilt from the originals.
