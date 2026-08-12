# Chronicler — Project Assessment

Date: 2026-08-13 · Scope: full source tree (`chronicler/`, `tests/`, docs, CI)

## Verdict

The architecture is sound and the docs are unusually good for a pre-alpha. The problem is
not design, it's that **the documentation and TODO.md describe a system that doesn't exist yet**.
Roughly a third of the checked boxes in `TODO.md` are aspirational, two of the four advertised
deployment modes crash or are stubbed out, and one endpoint hands out the API key to anyone
who asks.

The fastest path back to momentum is not new features. It is: fix the four blockers below,
make CI actually fail on breakage, and re-baseline `TODO.md` against reality.

---

## 1. Blockers (fix before anything else)

### 1.1 `chronicler server` crashes on startup

`TagRepository` declares `search()` as `@abstractmethod`
(`chronicler/core/repositories.py:46`). `SQLiteTagRepository` implements `get_all`, `create`
and `delete` but **not** `search` (`chronicler/core/sqlite/tag_repository.py`).

`server/main.py:42` registers `SQLiteTagRepository` as the factory for `TagRepository`, and
`SearchService` depends on it. The first `container.resolve(SearchService)` in
`RpcServer.build()` therefore raises:

```
TypeError: Can't instantiate abstract class SQLiteTagRepository
           with abstract method search
```

Server mode has no test coverage (`tests/__pycache__/test_server_routes.cpython-312.pyc` exists
but the `.py` is gone), which is why this went unnoticed.

**Fix:** implement `search` on `SQLiteTagRepository`, and add a smoke test that builds the
server app.

### 1.2 The web client leaks the API key to unauthenticated callers

```python
# chronicler/webclient/main.py:19
@app.get("/config")
async def get_config():
    return {"server_url": ..., "api_key": settings.api_key}
```

No auth, bound to `0.0.0.0:8080` by default. Anyone on the network gets full server credentials.

**Fix options, in order of preference:**

1. Make the web client a true reverse proxy: the browser talks to the web client, the web
   client injects `X-API-Key` server-side. The key never reaches the browser.
2. If the browser must hold a credential, issue a short-lived scoped session token behind a
   login, not the master key.

Related: `RpcServer.build()` sets `allow_origins=["*"]` **with** `allow_credentials=True`
(`rpc.py:112`) — an invalid and unsafe CORS combination. Also, API key comparison
(`rpc.py:100`) should use `secrets.compare_digest`.

### 1.3 Path traversal in `/upload`

```python
# chronicler/core/rpc.py:128
file_path = upload_dir / file.filename
```

`file.filename` is client-controlled. `../../.ssh/authorized_keys` escapes the imports
directory. There is also no size limit, no content-type check, and no collision handling.

**Fix:** `Path(file.filename).name` at minimum; better, generate a server-side UUID name and
store the original name as metadata. Add a max upload size.

Note: `python-multipart` is required for this endpoint but is only in the `server` extra,
not in `requirements.txt` — so the endpoint 500s in the default dev install.

### 1.4 Remote task payloads are trusted

`TaskService.queue_import` accepts an arbitrary `file_path` **and** an arbitrary `regex` from
the caller, and `WorkerHandlers.handle_import` opens that path directly (`handlers.py:38`).
Over the RPC API this is arbitrary file read on the server, plus ReDoS via a crafted regex.

**Fix:** confine `file_path` to the workspace/imports directory (resolve and check
`is_relative_to`), and either whitelist import profiles or run the regex with a timeout.

---

## 2. Correctness and concurrency

### 2.1 One `AsyncSession` shared by everything

- `DesktopApp.main()` opens a single archive session (`app.py:69`) and hands it to both the
  repositories used by the UI *and* the `WorkerManager` running in `asyncio.create_task`.
- `server/main.py:39` registers `AsyncSession` as a container **singleton**, so every
  concurrent HTTP request shares one session.

`AsyncSession` is not safe for concurrent use. Expect intermittent
`IllegalStateChangeError` / "session is already flushing" under any real load, and cross-request
identity-map bleed.

**Fix:** session-per-operation (or per-request via a FastAPI dependency). Repositories should
take a `session_factory`, or a unit-of-work object, rather than a live session.

### 2.2 Project sessions leak

`DesktopApp.update_view()` (`app.py:145`) opens a project session on every navigation to a
transcript and never closes it. `DatabaseManager` also caches engines per chronicle id forever
with no eviction.

### 2.3 The worker loop is not what the docs claim

`ARCHITECTURE.md` describes Scribes with per-provider concurrency and a
`Pending → Claimed → Running` lifecycle. `WorkerManager` (`core/workers.py`) actually:

- polls every 1s and runs pending tasks **strictly sequentially** in one coroutine;
- has **no atomic claim** — `get_pending()` then `update_status()` is a race, so two
  processes (desktop + server against the same workspace) will both run the same task;
- has **no retry** despite `TODO.md` marking "Retry support" complete;
- never uses `TaskStatus.WAITING`, and `TaskStatus.PENDING`/`WAITING` are redundant.

**Fix:** atomic claim via a conditional `UPDATE ... WHERE status='PENDING'` returning rowcount,
a `claimed_by`/`claimed_at` column, plus `attempts`/`max_attempts` for retry. Then a bounded
worker pool per task type.

### 2.4 Destructive processing with no safety net

Both `handle_import` and `handle_clean` call `repo.delete_all()` before writing
(`handlers.py:58`, `handlers.py:100`). A crash mid-clean destroys the transcript with no
backup and no way to undo. The clean path also drops all speakers and recreates them, so
speaker IDs change on every clean — any future annotation keyed on speaker id will break.

**Fix:** wrap in a single transaction, or write to a new revision and swap.

### 2.5 Hand-rolled migrations will bite

`DatabaseManager._migrate_schema_sync` only ever *adds* columns, guesses defaults from type
names, and interpolates values into raw SQL. It cannot handle renames, drops, type changes or
index creation — and there is no schema version stamp anywhere.

**Fix:** adopt Alembic now, while there are zero real users. Two migration chains (archive and
project) is a supported Alembic pattern.

### 2.6 Smaller correctness issues

| Location | Issue |
|---|---|
| `services/search_service.py` | Every method is a `pass` stub returning `None` — yet it is `@service`-registered, so the API exposes five endpoints that always return `null`. |
| `services/transcript_service.py:14` | `update_line` returns the input unchanged. Transcript editing does not persist. |
| `sqlite/transcript_repository.py:76` | `search` is `pass`. No SQLite FTS anywhere, despite `ARCHITECTURE.md` claiming "Current implementation uses SQLite Full-Text Search". |
| `desktop/views/archive.py:366-383` | `on_click=lambda ...: self.clean_clicked(i)` returns an un-awaited coroutine. These buttons likely do nothing. |
| `desktop/views/archive.py:277` | `page.snack_bar = ...` is the pre-0.70 Flet API. On flet 0.86 use `page.open(ft.SnackBar(...))`. No snackbar is shown today. |
| `desktop/views/archive.py:218` | "Import Audio" queues a `TaskType.IMPORT`, which `handle_import` opens as UTF-8 text. Guaranteed `UnicodeDecodeError`. There is no audio importer. |
| `core/config.py:24-43` | Three bare `except: pass` blocks swallow malformed config silently — the user sees "no config" instead of "your YAML is broken". |
| `core/config.py:117` | `get_settings` is `@lru_cache`d and mutated in place by the wizard; there is no invalidation path. Fragile. |
| `core/wizard.py:68-72` | Thin-client setup *generates* an API key when the user leaves it blank. That key cannot possibly match the server's. |
| `core/wizard.py` | The chosen mode is never persisted — there is no `mode` field on `Settings`, contradicting the README's "the active mode is determined by the application configuration". |
| `desktop/views/settings.py` | Entirely static mock. "Local workspace: Not configured" is hardcoded; the dark-mode switch is inert. |
| `desktop/views/tasks.py` | No polling, so progress never updates live; no retry button. |
| `desktop/views/transcript.py:32` | `read_only=True`, and the Export button has no `on_click`. |
| `core/models.py` | `Chronicle.duration` is a `str`; `speakers_count` is denormalised and never written. |
| `core/database.py:34` | `String(1000)` etc. are meaningless in SQLite but will silently truncate if you ever move to Postgres. Transcript `text` is unbounded `String` — fine now, worth a comment. |

---

## 3. Architecture gaps vs. the documented design

| Documented | Actual |
|---|---|
| DI container resolves services in all modes | `DesktopApp` constructs everything by hand (`app.py:71-80`). `Container` is used only by the server. `TODO.md` admits this. |
| Thin Client mode | `desktop/main.py:24` prints "not yet fully implemented" and `sys.exit(1)`. `RemoteContainer` exists and is tested, but nothing wires it into the UI. |
| Server runs background Scribes | `server/main.py` never creates a `WorkerManager`. Queued tasks on a server are never executed. |
| Providers registered by annotation | Handlers are registered imperatively in `app.py`. The `@service` decorator exists; there is no `@provider`. |
| Tags stored in `project.db` for portability | Tags live in the archive DB only (`database.py`), so a shared Chronicle loses its tags. `TODO.md` has this unchecked. |
| Chronicle full-text search | Not implemented at any layer. |

**Recommendation:** the seam that makes the four deployment modes work is
`Container` vs `RemoteContainer`. Right now only one consumer uses it. Refactoring `DesktopApp`
to resolve services from a container is the single highest-leverage change in the codebase —
it unblocks Thin Client mode for free and removes the hand-wiring.

---

## 4. Tests and CI

**Test suite is structurally confused.** Two parallel layouts coexist:

```
tests/test_search.py            tests/chronicler/core/test_services.py
tests/test_importers.py         tests/chronicler/core/test_importers.py
```

`tests/test_search.py` and `tests/chronicler/core/test_services.py` test the same two service
methods. Pick the mirrored layout (`tests/chronicler/...`) and move everything into it.

**Deleted tests.** `tests/__pycache__/` contains `.pyc` files for six tests whose sources are
gone: `test_server_routes`, `test_config_validation`, `test_wizard_api_key`, `test_wizard_partial`,
`repro_issue`, `repro_404`. `.gitignore` correctly excludes `__pycache__`, so these are untracked
local leftovers rather than a hygiene problem — but they are evidence that a server-routes test
and two wizard tests existed and were removed. Worth recovering from git history to see whether
they were dropped because they failed.

**Coverage gaps that map directly to the blockers above:**

- No test builds the server app → §1.1 shipped undetected.
- No test asserts `/config` doesn't leak secrets → §1.2.
- No test for `WorkerManager` concurrency or claim semantics.
- No test for `DatabaseManager._migrate_schema_sync`.
- No test exercises `SQLiteTagRepository` at all.

**CI does not gate anything.** All three quality steps carry `continue-on-error: true`
(`.github/workflows/continuous-integration-workflow.yml:64,69,74`). Ruff, flake8 and mypy can
all fail and the build is green. Coverage is uploaded but no threshold is enforced.

Also: running both ruff and flake8 is redundant — ruff covers flake8's rules. Drop flake8.
And the `.venv` cache is restored across jobs by absolute path, which will break the moment you
re-enable the `macos-latest` matrix entry (line 86).

---

## 5. Suggested plan

### Sprint 1 — Stop the bleeding (~1 week)

1. Implement `SQLiteTagRepository.search`; add a server-build smoke test. *(§1.1)*
2. Remove the API key from `/config`; proxy requests server-side. *(§1.2)*
3. Sanitise upload filenames; add a size cap; move `python-multipart` into base deps. *(§1.3)*
4. Confine import `file_path` to the workspace. *(§1.4)*
5. Fix CORS; use `compare_digest` for the key. *(§1.2)*
6. Drop `continue-on-error` from CI; delete flake8; fix whatever ruff/mypy then surfaces.
7. Recover the six deleted tests from git history and see why they went.

### Sprint 2 — Make the foundation honest (~2 weeks)

8. Session-per-operation. Repositories take a factory, not a live session. *(§2.1, §2.2)*
9. Atomic task claiming + retry + `attempts` column. *(§2.3)*
10. Wrap import/clean in transactions; stop recreating speakers. *(§2.4)*
11. Introduce Alembic for both schemas. *(§2.5)*
12. Consolidate the test layout; add `WorkerManager` and migration tests.
13. **Re-baseline `TODO.md`** — uncheck: task claiming, retry support, edit text, chronicle
    search, and anything else §3 contradicts.

### Sprint 3 — Deliver the promised modes (~2 weeks)

14. Refactor `DesktopApp` onto `Container`. *(§3)*
15. Select `Container` vs `RemoteContainer` from settings → Thin Client works.
16. Start a `WorkerManager` in server mode.
17. Persist `mode` in `Settings`; fix the wizard's key-generation footgun.
18. Wire `SettingsView` to real settings.

### Sprint 4 — First genuinely useful feature

19. Pick **one** vertical and finish it end to end. Recommendation: **export** (plain text +
    Markdown). It's small, it has no new dependencies, and it makes the app *do something*
    a user would come back for.
20. Then transcript editing (persist `update_line`), then FTS search, then Whisper.

Deliberately deferred: audio import, transcription, AI analysis, semantic search. Each is
weeks of work and none of them matter while server mode crashes on boot.

---

## 6. What's genuinely good

Worth saying, because it's why this project is worth finishing:

- The `@service` → RPC-endpoint → `RemoteServiceProxy` generation is elegant, and
  `tests/test_rpc_framework.py` proves the round trip works with real Pydantic types. That's the
  hard part of the multi-mode design and it's already done.
- The self-contained-Chronicle storage model is a genuinely good decision, and the "use the
  sync tool you already trust" reasoning in the README is right.
- `ARCHITECTURE.md` is clear enough that the gaps in §3 were findable by reading it against
  the code. Most pre-alpha projects don't have that.
- Repository interfaces are clean and the SQLite implementations are readable.
- The Flet UI, mock data notwithstanding, has a coherent shape.

The gap is execution depth, not direction.
