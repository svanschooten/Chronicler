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
> tested. Remaining work is Sprint 2 (§2 in ASSESSMENT.md: session-per-operation, atomic
> task claiming/retry, transactional import/clean, Alembic) and Sprint 3 (DesktopApp onto
> the Container, Thin Client mode, server-mode worker manager).

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
  bound — see the new item under Phase 3 below.
* [x] **CI gates nothing.** `continue-on-error` removed from ruff/mypy; flake8 dropped
  (100% overlap with ruff, confirmed by running both); `--cov-fail-under=68` added
  (measured baseline was 70.4%).

Still open:

* [ ] **One `AsyncSession` shared everywhere.** UI, worker loop and every HTTP request share a
  single session. Not concurrency-safe. Sprint 2.

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
    * [x] Enforce a coverage threshold (`--cov-fail-under=68`, added 2026-08-13)
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
* [ ] Task claim columns (`claimed_by`, `claimed_at`) and `attempts` / `max_attempts`

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

* [ ] Replace `DatabaseManager._migrate_schema_sync` with Alembic
    * The current implementation only adds columns, guesses defaults from type names,
      interpolates values into raw SQL, and stores no schema version.
* [ ] Baseline migration for the archive database
* [ ] Baseline migration for the project database

---

# Phase 3 — Worker framework

* [x] Create worker manager
* [x] Create worker lifecycle
* [x] Persistent task handling (store tasks in master database)
* [ ] **Task claiming** — reopened. `get_pending()` followed by `update_status()` is a race;
  two processes against one workspace will both run the same task.
* [~] Task status tracking: WAITING, WORKING, DONE, FAILED
    * `WAITING` is never used, and `PENDING` / `WAITING` are redundant.
* [x] Task progress tracking
* [x] Error handling
* [ ] **Retry support** — reopened. Nothing ever moves a FAILED task back to PENDING, and
  there is no attempt counter.
* [ ] Implement annotation-based provider registration — handlers are still registered
  imperatively in `desktop/app.py`
* [ ] Implement Scribe workers with concurrency configuration — the loop is strictly
  sequential in a single coroutine
* [ ] Run a worker manager in server mode (server mode currently executes no tasks at all)
* [ ] **Per-task CPU timeout.** Sprint 1 added a static pre-filter for catastrophic-backtracking
  regex patterns (`chronicler/core/processing/regex_guard.py`) but that's a shape check, not
  a CPU-time bound — Python threads can't be force-killed and CPython's regex matcher
  doesn't release the GIL during backtracking, so a real bound needs a subprocess-based
  watchdog. Build this as a general per-task timeout in the worker loop (not
  regex-specific) when doing the concurrency/atomic-claiming rework above, rather than
  building a one-off version now and redoing it here.

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
* [ ] Make import/clean transactional — both call `delete_all()` before rewriting, so a crash
  mid-run destroys the transcript
* [ ] Stop recreating speaker rows on every clean (speaker IDs change each run)

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
* [ ] Worker claiming and retry tests
* [ ] Migration tests
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
