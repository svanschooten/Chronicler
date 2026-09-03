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

## Sessions

`get_archive_session()` returns a new session each call. Project engines are cached per
chronicle id, because creating one runs the migration chain.

The rule that matters: **the worker loop's session is never shared with the UI or with
HTTP request handling.** Those run as separate coroutines on the same event loop, so an
await in either can interleave with the other's in-flight operation, and `AsyncSession`
does not allow that on a shared instance. `build_worker_runtime` therefore hands its
session back to the caller rather than hiding it — whoever starts the loop owns closing
it.

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
