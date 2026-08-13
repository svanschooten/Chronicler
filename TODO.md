# Chronicler Roadmap

**Status legend**

| Mark  | Meaning                                                                 |
| ----- | ---------------------------------------------------------------------- |
| `[x]` | Implemented and covered by tests                                       |
| `[~]` | Partially implemented — see the note; do not assume it works end to end |
| `[ ]` | Not started                                                            |

> Re-baselined 2026-08-13 against the actual source tree. Several items previously marked
> complete were documentation-only or stubbed; they have been reopened. See
> [ASSESSMENT.md](ASSESSMENT.md) for the full analysis.
>
> Sprint 1 ("stop the bleeding") landed 2026-08-13: all six items below are fixed and
> tested. Sprint 2 ("make the foundation honest") also landed 2026-08-13:
> session-per-operation, atomic task claiming/retry, transactional import/clean, and
> Alembic are all done. Remaining work is Sprint 3 (DesktopApp onto the Container, Thin
> Client mode, server-mode worker manager) and Sprint 4 (first genuinely useful feature).

---

## Known blockers

Fixed in Sprint 1 (2026-08-13):

* [x] **Server mode cannot start.** `SQLiteTagRepository.search` implemented; server-build
  smoke test added (`tests/chronicler/core/test_server_main.py`).
* [x] **Web client leaks the API key.** Web client is now a true reverse proxy
  (`POST /api/{service}/{method}`, `POST /api/upload`); `GET /config` no longer returns
  `api_key`. Also fixed alongside: CORS `allow_credentials` was `True` with a wildcard
  origin (invalid/unsafe combo), API key comparison now uses `secrets.compare_digest`.
* [x] **Path traversal in `/upload`.** On-disk filenames are now server-generated
  (`uuid4()` + whitelisted extension); a 500MB size cap is enforced with cleanup of
  partial files; `python-multipart` moved into `requirements.txt`.
* [x] **Import tasks trust client input.** `file_path` is confined to the imports
  directory in `handle_import` (`is_relative_to` check). `regex` is statically checked
  for catastrophic-backtracking shapes (`chronicler/core/processing/regex_guard.py`)
  before a task is even created. Note: the static check is a pre-filter, not a CPU-time
  bound — see the note under Phase 3 below.
* [x] **CI gates nothing.** `continue-on-error` removed from ruff/mypy; flake8 dropped
  (100% overlap with ruff, confirmed by running both); `--cov-fail-under` added.

Fixed in Sprint 2 (2026-08-13):

* [x] **One `AsyncSession` shared everywhere.** UI, worker loop and every HTTP request used
  to share a single session — real crash risk (`IllegalStateChangeError`) under any
  concurrent use. `RpcServer` now resolves a fresh `Container` scope per request
  (`Container.create_scope()`); `DesktopApp`'s `WorkerManager` gets its own dedicated
  session, never touched by the UI, and `update_view()` opens a fresh session per
  navigation instead of holding one for the app's lifetime. Verified live: 30 concurrent
  requests against a real server, no errors.

New known limitation (Sprint 2, 2026-08-13):

* [ ] **No upgrade path from a pre-Alembic workspace.** Adopting Alembic (below) means any
  workspace created before this sprint will fail to start (`table already exists`) —
  verified concretely against a real pre-existing `chronicler.db`. `alembic stamp head`
  clears the crash but doesn't verify schema compatibility, so a stamped-but-actually-old
  database (e.g. missing the `claimed_by`/`attempts` columns added this sprint) would be
  marked "up to date" while genuinely incomplete — worse than the crash. Matches this
  project's own reasoning for adopting Alembic now ("while there are zero real users") —
  pre-Alembic workspaces should be deleted and recreated, not migrated in place. The one
  local dev workspace affected (`~/ChroniclerWorkspace`) was cleared and recreated fresh
  2026-08-13 at the user's request (disposable test data, not real content) — confirmed
  the fresh workspace stamps correctly at head with the full current schema.

---

## Phase 0 — Project foundation

* [x] Create repository structure
* [x] Configure Python package
* [x] Add development dependencies
* [x] Add formatting tools
* [x] Add linting
* [~] Add GitHub Actions CI
    * [x] Optimized multi-job workflow with caching
    * [x] Make quality checks blocking (`continue-on-error` removed 2026-08-13)
    * [x] Drop flake8 (redundant with ruff — removed 2026-08-13)
    * [x] Enforce a coverage threshold (`--cov-fail-under=74`, re-measured 2026-08-13
      after Sprint 2 - baseline was 76.2%)
    * [ ] Fix `.venv` cache reuse before re-enabling the macOS matrix entry

---

# Phase 1 — Application foundation

## Configuration

* [x] Create application settings system
* [x] Store user configuration in OS config directory
* [x] Create first-run wizard
* [x] Select workspace location
* [x] Validate workspace permissions
* [~] Automatic configuration validation for different run modes
    * Validation exists, but the chosen mode is never persisted — there is no `mode` field on
      `Settings`, so "the active mode is determined by the configuration" is not yet true.
* [x] Use argparse for command-line arguments and --verbose mode
* [ ] Persist the deployment mode in settings
* [x] Stop generating an API key when the user leaves it blank in thin-client setup
    * Fixed 2026-08-13: `RemoteServerStep` now re-prompts with an explanation instead of
      generating a key that can't possibly match the server's.
* [x] Surface config parse errors instead of swallowing them (`except: pass` in `config.py`)
    * Fixed 2026-08-13: logs a warning naming the broken file; falls back to defaults
      the same way it did before (behavior-preserving, just no longer silent).

## Architecture alignment

* [x] Implement DI container for service resolution
* [ ] Refactor DesktopApp to use DI container — still wires everything by hand in `app.py`
* [ ] Support switching between local and remote services based on settings
* [ ] Ensure all business logic is strictly in Services

---

## Backend abstraction

* [x] Define repository interfaces
* [x] Separate services from storage
* [~] Create local storage backend
    * `SQLiteTagRepository.search` implemented 2026-08-13 (was the server-startup
      blocker). `SQLiteTranscriptRepository.search` now raises `NotImplementedError`
      rather than silently returning `None` against a `list[...]` annotation, but the
      actual full-text search still isn't implemented — see Phase 6.
* [ ] `Container.register_factory`'s generics don't fit the interface-to-implementation
  registration pattern it's used for — mypy flags every
  `register_factory(AbstractRepo, ConcreteImpl)` call as `[type-abstract]`. Worked around
  with targeted `# type: ignore[type-abstract]` for now (`server/main.py`,
  `test_server_main.py`); worth revisiting the container's type signature directly.
* [ ] `DatabaseManager._project_engines` caches an engine per chronicle id forever, no
  eviction. Not corrupting anything (each chronicle's engine is independent), just a slow
  resource leak in a long-running process that opens many distinct chronicles. Deferred
  during the Sprint 2 session-scoping work — a proper fix (LRU with a size cap) is easy to
  get subtly wrong (evicting an engine mid-use) and lower severity than what that sprint
  actually fixed.
* [x] Prepare remote API backend interface — `RemoteContainer` / `RemoteServiceProxy`, tested

Goal:

The UI and services should not depend directly on SQLite.

---

# Phase 2 — Chronicle storage

## Archive database

* [x] Projects/Chronicles table
* [x] Tags table
* [~] Chronicle/tag relationship
    * The `chronicle_tags` table and relationship exist, but nothing ever writes to them.
      There is no tag service, no tag API and no tag UI.
* [x] Persistent task table
* [x] Task claim columns (`claimed_by`, `claimed_at`) and `attempts` / `max_attempts`
    * Added 2026-08-13 along with `SQLiteTaskRepository.claim_next()`, an atomic claim.

---

## Chronicle database

* [~] Chronicle metadata
    * `DBProjectMetadata` is declared but never read or written anywhere in the codebase.
* [x] Speakers
* [x] Transcript lines
* [ ] Tags (in project.db for portability)
* [ ] AI analysis results
* [ ] Cleanup state

---

## Schema management

* [x] Replace `DatabaseManager._migrate_schema_sync` with Alembic
    * Done 2026-08-13. Two independent chains (`chronicler/migrations/archive`,
      `chronicler/migrations/project`), invoked programmatically (no static
      `alembic.ini` - the project chain runs against a different file per chronicle).
      Known limitation: no upgrade path from a pre-Alembic workspace - see "Known
      blockers" at the top of this file.
* [x] Baseline migration for the archive database
* [x] Baseline migration for the project database

---

# Phase 3 — Worker framework

* [x] Create worker manager
* [x] Create worker lifecycle
* [x] Persistent task handling (store tasks in master database)
* [x] **Task claiming**
    * Fixed 2026-08-13: `SQLiteTaskRepository.claim_next(worker_id)` does a conditional
      `UPDATE ... WHERE status='PENDING'` + rowcount check - atomic, safe under
      concurrent callers (two processes against one workspace no longer double-run a
      task).
* [x] Task status tracking: WORKING, DONE, FAILED
    * `WAITING` removed 2026-08-13 - confirmed unused anywhere in the codebase.
* [x] Task progress tracking
* [x] Error handling
* [x] **Retry support**
    * Fixed 2026-08-13: `attempts`/`max_attempts` columns, `mark_failed_or_retry()`
      resets a task to PENDING (below max_attempts) instead of FAILED.
      `WorkerManager.process_tasks()` bounds each poll cycle to what was pending when
      the cycle started, so retries spread across poll cycles rather than all firing
      instantly in one burst.
* [ ] Implement annotation-based provider registration — handlers are still registered
  imperatively in `desktop/app.py`
* [ ] Implement Scribe workers with concurrency configuration — the loop is strictly
  sequential in a single coroutine
* [ ] Run a worker manager in server mode (server mode currently executes no tasks at all)
* [ ] **Per-task CPU timeout.** The regex ReDoS guard (`chronicler/core/processing/
  regex_guard.py`) is a static shape check, not a CPU-time bound — Python threads can't
  be force-killed and CPython's regex matcher doesn't release the GIL during
  backtracking, so a real bound needs a subprocess-based watchdog. Build this as a
  general per-task timeout in the worker loop (not regex-specific) rather than a
  one-off version.

Initial tasks:

* [~] IMPORT — text only; audio files are queued as IMPORT and crash on UTF-8 decode
* [ ] TRANSCRIBE
* [x] CLEAN
* [ ] EXPORT

Future:

* [ ] AI_ANALYSIS
* [ ] AI_SUMMARIZE
* [ ] GRAPH_ANALYZE

---

# Phase 4 — Desktop application

## UI

* [x] Application shell
* [x] Navigation
* [~] Theme support — hardcoded dark mode; the Settings toggle is inert

---

## Archive view

* [x] Browse Chronicles
* [~] Implement search in repositories and services
    * [x] Workspace search (chronicle title only, `ILIKE`)
    * [ ] Chronicle search (Full-text search using SQLite FTS)
    * [ ] `SearchService` — all five methods are `pass` stubs that return `None`, yet are
      registered as RPC endpoints
* [x] Search UI in Archive view
* [ ] Filter by tags
* [x] Open Chronicle
* [x] Import Transcript (via Header)
* [ ] Fix un-awaited coroutines in card action callbacks (`clean_clicked`, per-card imports)
* [ ] Fix snackbars — `page.snack_bar = ...` is the pre-0.70 Flet API and no longer displays

---

## Create Chronicle wizard

* [x] Select files
* [ ] Assign speakers
* [ ] Enter metadata
* [ ] Add tags
* [x] Create Chronicle (Basic implementation)

---

## Task monitor

* [x] View active tasks
* [~] Show progress — rendered, but the view never polls, so it does not update live
* [ ] Retry failures

---

## Settings view

* [ ] Replace the static mock with real settings — workspace path, connection mode and theme
  are all hardcoded strings today

---

# Phase 5 — Processing

## Import

* [ ] Audio importer
* [ ] File validation
* [x] Import worker
* [x] Regex importer
* [x] Confine import paths to the workspace
    * Fixed 2026-08-13: enforced in `handle_import` (resolve + `is_relative_to` against
      the imports directory), at the point of file access, so it covers any caller.
* [~] Bound regex execution (ReDoS)
    * Static pre-filter added 2026-08-13 (`regex_guard.py`) — rejects patterns over 500
      chars and patterns shaped for catastrophic backtracking. Not a CPU-time bound; see
      the new item under Phase 3.

---

## Transcription

* [ ] Whisper integration
* [ ] Transcription worker
* [ ] Timestamp handling
* [ ] Speaker assignment
* [ ] Retry support

---

## Cleanup

* [x] Cleanup worker
* [x] Text normalization
* [x] Segment merging
* [ ] Cleanup markers
* [x] Make import/clean transactional
    * Fixed 2026-08-13: repository methods no longer commit internally; `handle_import`/
      `handle_clean` commit once at the end, rollback + re-raise on any exception.
* [x] Stop recreating speaker rows on every clean (speaker IDs change each run)
    * Fixed 2026-08-13: `delete_all()` renamed to `delete_all_lines()` and no longer
      touches `DBSpeaker` - `get_or_create_speaker()`'s lookup-by-name now naturally
      reuses the same row across re-imports/cleans.

---

# Phase 6 — Editing and export

## Transcript viewer

* [x] Display transcript
* [ ] **Edit text** — reopened. The text field is `read_only=True` and
  `TranscriptService.update_line` returns its input without persisting.
* [ ] Search within Chronicle

Future:

* [ ] Audio synchronization
* [ ] Timestamp editing

---

## Export

Initial:

* [ ] Plain text export
* [ ] Markdown export
* [ ] Wire up the Export button in the transcript view (currently has no handler)

Future:

* [ ] PDF
* [ ] DOCX
* [ ] HTML

---

# Phase 7 — Chronicler Server

* [x] Add server application mode
* [x] Add first run CLI wizard
    * [x] Add option to generate or set API key
* [x] Add API layer
* [x] Add authentication
    * Fixed 2026-08-13: key comparison uses `secrets.compare_digest`; CORS
      `allow_credentials` set to `False` (was `True` alongside a wildcard origin — an
      invalid, unsafe combination, and unnecessary since auth is a header, not a cookie).
* [ ] Add server storage management
* [x] Add remote repository implementation
* [ ] Connect desktop client to server
* [x] Fix server startup (see Known blockers)
* [x] Harden `/upload` — filename sanitisation, size limit, collision handling
    * Fixed 2026-08-13: server-generated `uuid4()` filenames (whitelisted extension
      only), 500MB size cap with partial-file cleanup on overflow, collisions are
      statistically impossible by construction.
* [x] Move `python-multipart` into base dependencies (`/upload` 500s without it)

---

# Phase 8 — Web Client

* [x] Implement basic web client server
* [x] Serve static files
* [x] Implement API proxy or CORS support for Chronicler Server
    * Fixed 2026-08-13: `POST /api/{service}/{method}` and `POST /api/upload` proxy to
      the upstream server with `X-API-Key` injected server-side. The browser never sees
      the key. `GET /config` now returns only `{"connected": bool}`.
* [x] Web Client Configuration in Wizard (Option to set up as a Web Client server)
* [x] Basic UI for browsing Chronicles
* [x] Basic UI for creating Chronicles
* [x] UI for importing audio files via upload
* [ ] Basic UI for viewing a Chronicle
* [ ] Shared-password login with a signed session cookie
* [x] Stop exposing the upstream server URL to the browser

---

# Phase 9 — Distribution

* [ ] GitHub Actions builds
* [ ] Automated releases
* [ ] Windows package
* [ ] macOS package
* [ ] Linux package

Possible tools:

* PyInstaller
* Nuitka

---

# Testing

* [x] Repository tests (chronicle, task)
* [x] Container tests
* [x] RPC round-trip tests (server + remote proxy)
* [x] Importer and cleaner tests
* [x] Consolidate the duplicated flat and mirrored test layouts under `tests/chronicler/`
    * Done 2026-08-13. This was also a live break, not just duplication: two files
      named `test_importers.py` with no `__init__.py` anywhere under `tests/` made
      pytest's rootless collection abort with `import file mismatch` — a plain `pytest`
      invocation couldn't run the suite at all.
* [x] Investigate six deleted tests whose stale `.pyc` remain on disk — `test_server_routes`,
  `test_config_validation`, `test_wizard_api_key`, `test_wizard_partial`, `repro_issue`,
  `repro_404`.
    * Investigated 2026-08-13: none are in git history (`git log --all --diff-filter=D`
      and full reflog both checked) — they were written and deleted locally without ever
      being committed, so there's nothing to restore. `test_server_routes`,
      `test_config_validation` and `test_wizard_api_key`/`test_wizard_partial` were
      reconstructed as real coverage from their names' evident intent.
      `repro_issue`/`repro_404` were not — no surviving signal (docstring, linked issue,
      commit) of what they targeted, so reconstructing them would just be guessing.
* [x] Server startup smoke test
* [x] Web client auth / proxy tests
* [x] Worker claiming and retry tests (added 2026-08-13)
* [x] Migration tests (added 2026-08-13 — `alembic_version` stamped at head, idempotent
  re-init/re-open)
* [x] `SQLiteTagRepository` tests (was zero coverage, fixed 2026-08-13)

---

# Future ideas

## Collaboration

* [ ] Multiple users
* [ ] Permissions
* [ ] Shared Chronicles
* [ ] Conflict handling

## Intelligence

* [ ] Summaries
* [ ] Action items
* [ ] Topic extraction
* [ ] Semantic search
* [ ] Embeddings
