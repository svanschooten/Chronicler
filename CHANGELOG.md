# Changelog

What landed, newest first. Open work is in [tickets/](tickets/README.md), and the longer
direction in [ROADMAP.md](ROADMAP.md). The release number lives in
`chronicler/__init__.py`.

Entries up to the audit's wave 4 were written at the time, in the old `TODO.md`, and are
kept as they were: a note that a later change superseded something says so in italics.
A ticket number such as 063 refers to its file in [tickets/](tickets/README.md), which
holds the problem and its evidence.

| Sprint | Theme | Landed |
| ------ | ----- | ------ |
| 1 | Stop the bleeding — server startup, API-key leak, path traversal, CI that gates | 2026-08-13 |
| 2 | Make the foundation honest — session-per-operation, atomic task claiming/retry, transactional import/clean, Alembic | 2026-08-13 |
| 3 | Deliver the promised modes — DI-resolved DesktopApp, working thin client, worker in server mode, real SettingsView | 2026-08-13 |
| 4 | The core loop — Chronicle CRUD, audio import, faster-whisper TRANSCRIBE, plain-text export, and four rounds of UI fixes found by actually running the app | 2026-08-13 |
| 5 | Structure and hygiene — see below | 2026-08-17 |
| 6 | Low-hanging fruit — see below | 2026-08-17 |
| 7 | Configurability foundation — settings sections, i18n, cleaning pipeline, audio source records | 2026-09-03 |
| 8 | Transcription parameters, editable settings, SRT export, speaker registry, thin-client handshake | 2026-09-03 |
| 9 | Normalisation, LLM summarisation, recording, setup wizard, character designer extraction | 2026-09-03 |
| 9.1 | Migration serialisation, the normalization extra, actionable desktop-integration errors | 2026-09-03 |
| 10 | Install-on-demand extras, chronicle actions in the chronicle view, one transcribe dialog, capability gating, linking hydration | 2026-09-03 |
| 11 | Audit cleanup — explicit RPC exposure, full i18n with a guard, shared chronicle operations — then an editable transcript | 2026-09-03 |
| 11.1 | Document exports over RPC, chronicle zip export, the embedded-runtime build | 2026-09-17 |
| Audit 1-4 | The code audit's first four waves: tickets 001-028, 067 and 068, see below | 2026-11-10 |
| Audit 5-11 | Quick fixes, safety and search, progress and restore, then a transcript editor that reads like the transcript: see below | 2026-11-17 |

## The code audit, waves 5-11 (2026-11-10 to 2026-11-17)

* **Wave 5, quick fixes.** A failed link no longer leaves a broken chronicle, and Link
  works on a thin client (072). "Open folder" on a thin client no longer tries a server
  path (049). Dismissing a dialog no longer leaves its action waiting, or a recording
  running (073). A finished task's event survives a busy database (069). Config files are
  read as UTF-8 and saved atomically (054). Workspace validation runs (055). Checking
  extras no longer stalls startup (039). Slow imports are lazy (038). Version and status
  agree (061). Dependabot covers the shared setup action (070).
* **Wave 6, safety, then search.** A regex has a real timeout instead of a guard (035).
  Project databases use `NullPool` (031) and one helper owns project database access
  (032, closing 033). A chronicle records the schema it needs, so an older Chronicler
  refuses a newer chronicle clearly (074). Full-text transcript search, in a chronicle and
  across the workspace (063). CI runs the optional extras (044), and normalization
  decodes the file once (057). Remote callers cannot point a chronicle at any path (076),
  and the upload cap limits what is received (053).
* **Wave 7, what users notice next.** The task list can be cleared (077). Transcription
  reports real progress and can be cancelled (064). Service errors reach thin clients
  with their explanation (046). The last 17 interface strings are translated (047). A
  server is set up with flags instead of the console wizard (042). A snapshot can be
  restored after a destructive action (065). Saving the edit dialog keeps a computed
  duration (075). Archive search shows only the latest query's results (078). Odd model
  replies no longer crash a summary (079). Only audio files count as tracks (048). The
  summary recap is budgeted (050). Local models are kept and released sensibly (052).
  Zip exports stream rather than holding everything in memory (037). The transcript
  editor builds only the rows on screen (056).
* **Wave 8, docs.** The top-level docs match the code (060), and `TODO.md` became this
  changelog, [ROADMAP.md](ROADMAP.md) and [docs/live-updates.md](docs/live-updates.md)
  (062).
* **Wave 11, a transcript editor that reads like the transcript.** Clicking a picker no
  longer empties it (086). Typing a speaker in different case reuses the speaker (083).
  Edit mode shows the transcript as text and opens a control only where clicked (082).
  A new speaker can be added from the picker (084). Alt+arrows move the open field to the
  next or previous line (085).

* **Wave 10, simplify the foundations.** The worker and its handlers: one class per task
  type instead of one built by inheritance, one `reconcile` for a chronicle's derived
  fields where five backfills were, a plain `claim_next`, and no sync-handler branch (040).
  A speaker is counted once per name on the lines, so a speaker with no lines no longer
  counts, and editing or deleting a line updates the count (051). The reflection-based
  container is gone: a `Services` object holds the four services for one unit of work,
  built by `local_services` or `remote_services`, and views take it (041). A chronicle's tags
  can be added and removed, and the archive can be narrowed to one tag (066).
  `TranscriptService` is split by topic: exports, audio sources and summaries are services
  of their own, the formatters moved to `core/exports/`, and `read_transcript_text`, the
  `GM` speaker style and the prototype `timestamp` lookups are gone (043). Routes moved
  with them, which is safe because client and server must run the same version.

Waves 9, 10 and 12 are still open.

## Sprints and earlier waves

### The code audit, waves 1-4 (2026-11-06 to 2026-11-10)

Tickets 001-028, 067 and 068 from the audit of `b02421a`. Each ticket file in
[tickets/](tickets/README.md) holds the problem and its evidence. In short:

* **A fresh install starts** (001), and tests can hold a database lock from a second
  connection (002).
* **CI runs on Windows too** (003, 005), and the CI and install files were trimmed
  (004).
* **Work is no longer lost.** Saving a speaker commits (006). The worker opens a short
  session per step, so one lock timeout no longer stops all background work (007). One
  process per workspace, enforced by an OS lock (008), whose failures say why (068).
  Interrupted tasks are recovered at start (009). Transcribing a second track for a
  speaker no longer deletes the first, because lines record their source (010). Clean
  asks first and snapshots the database (011).
* **Security.** The web client is gone (012, closing 013, 014 and 026). API keys are
  never logged, and secrets from the environment are never written to the config file
  (015). Released binaries can run as a server (016).
* **Correct output and robustness.** PDF export keeps every character (017). The
  default importer accepts non-ASCII speakers (018). Thin-client calls have sensible
  timeouts (019). Text-imported timings are flagged explicitly, so the subtitle guard
  survives edits (020). Reading an unknown chronicle no longer creates it (021). Retries
  back off (022). The model list is one call that carries its own error (023, closing 024).
  One `Mode` enum (025). A finished task refreshes the view in place (027). PDF and zip
  exports run off the event loop (028). The normalization extra installs numpy (067).

The review after wave 4 re-checked every open ticket, added tickets 072-081, and set the
order of the open waves.

### Sprint 11.1 — document exports over RPC, zip export, the embedded runtime (2026-09-17)

* **Document exports work on a thin client.** Methods returning `bytes` are served as
  `application/octet-stream`, so `export_html` and `export_pdf` could be exposed. See
  [docs/deployment-and-rpc.md](docs/deployment-and-rpc.md).
* **Chronicle zip export.** One chronicle packed as `project.db`, a `chronicle.json`
  manifest, and its audio when asked for. See [docs/storage.md](docs/storage.md) and the
  Export notes under [Notes by area](#notes-by-area).
* **The embedded-runtime build**, a launcher around a trimmed CPython that downloads
  optional components from hash-pinned locks. See
  [docs/runtime-build.md](docs/runtime-build.md).

### Sprint 11 — the audit's cleanup, then editing (2026-09-03)

Driven by the static-analysis pass; findings and rationale in the audit artifact and
`docs/deployment-and-rpc.md`, `docs/transcript-editing.md`.

* **RPC exposure is explicit.** `@service(expose=[...])`, validated at import time.
  Publishing every public coroutine made the API a side effect of whether a method
  happened to be async — two internal helpers became endpoints that way and served the
  server's absolute paths. Surface went from 45 methods to 31, with a test asserting each
  service's exact count.
* **The interface is fully translated, and stays that way.** Four views plus the forms
  were hardcoded English while the catalogue already held their keys. A new AST guard
  fails on a bare literal in any user-facing position — it found three more cases the
  hand audit had missed. Orphaned keys: 32 → 0.
  *(2026-11-10: not fully. Ticket 047 lists 17 strings in positions the guard does not
  check.)*
* **Chronicle operations are shared.** `desktop/operations.py` holds clean, identify
  speakers, import audio, import transcript, link, edit and delete; the archive card and
  the chronicle action row are both layout over it. They had already drifted.
* **SearchService deleted.** Five endpoints, two raising `NotImplementedError`, and no
  view resolved it — both search boxes already called the owning services directly.
* **Dead code removed** — `update_line` stub, `mark_source_transcribed`,
  `list_audio_source_paths`, `get_summary`, `ModelInfo.display_name`, `DBProjectMetadata`
  (plus a migration dropping its table), and `TaskType.PROCESS` / `EXPORT` / `TEST`.
* **`model_error` wired rather than deleted.** An empty model list now says why; an
  unreachable gateway used to look identical to a provider with no models.
* **`summary.max_tokens` → `chunk_token_budget`.** It never reached the model; the
  output cap is `llm.max_tokens`. Two settings with one name did different things.
* **Tests for `queue_summarize` and `queue_normalize`**, which shaped task payloads
  with nothing checking them. `importers.parse` split (McCabe 14 → 8).

#### Editable transcript

* **Per-line editing** behind a read/edit toggle. Whole-blob editing would have to
  guess where turns and timings belong; one control per line touches only what was typed
  into.
* **Timings are never touched by a text edit** — a corrected word must not shift the
  line off its audio.
* **Saves on blur, only when changed**, reverting and reporting on failure. Editing a
  line does not reload the list, which would drop the caret and scroll position.
* **Speakers come from the workspace-wide registry**, and a name typed while editing
  joins it.
* **Per-line delete confirms, quoting the line.** Transcript text is the one thing in
  a chronicle that cannot be regenerated — a re-transcription produces different words.

#### Shutdown

* **A session leaked for the life of the process.** `refresh_models` resolved
  `SystemService` off the root container, whose cache is never emptied, so its
  repository's `AsyncSession` was held open - with a read transaction - until the garbage
  collector terminated the connection at interpreter exit
  (`RuntimeError: greenlet is being finalized`). Reproduced exactly, fixed by resolving
  through a scope, and covered by four regression tests.
* **`Container.cached()`** - checking whether a scope built a session must not build
  one to find out.
* **The worker task is cancelled, not just flagged.** `stop()` only asks the loop to
  finish its current sleep.
* **The test suite is warning-free**, down from three SAWarnings that were hiding
  exactly this class of leak. *(2026-11-10: a plain run still is, but under `--cov` 4
  `ResourceWarning`s appear. Ticket 080.)*

1112 tests, 91% coverage; 1082 + 2 skipped with the extras hidden; ruff and mypy clean;
no warnings; thin-client check passes.

### Sprint 10 — the round of UI feedback (2026-09-03)

Nine pieces of feedback from running the app, grouped into what turned out to be seven
changes. Full plan and rationale: `docs/optional-extras.md`, `docs/desktop.md`.

* **Optional components install on demand, after asking.** `core/extras.py` is one
  registry for all four extras — module, requirement, size, and any system package pip
  cannot supply — replacing four hand-written "install the extra" strings that had
  drifted. `ExtraInstaller` confirms, installs off the UI thread, and re-checks. The
  confirmation offers "install without asking", which writes `extras.auto_install`
  (default `false`, also editable in Settings).
* **`is_available()` imports rather than looking.** `sounddevice` is a 32 kB binding
  with no bundled PortAudio: `find_spec` finds it and the import then raises `OSError`.
  The message tells the pip case and the apt case apart.
* **Chronicle actions live in the chronicle view too** — import audio, import
  transcript, clean, identify speakers, generate summary, edit, delete. `ImportCoordinator`
  and the forms moved to `desktop/` so both views share them.
* **One file-dialog flow.** `desktop/picking.py` replaces the archive view's
  `picker_action` state machine rather than letting a second view copy it.
* **One transcribe button, one dialog.** Speaker, language, model, silence threshold
  and normalize-first, all defaulting from Settings and applying to that run only.
  *Save speaker only* is now a labelled secondary action instead of a confirm button
  that said "Transcribe" while only assigning.
* **Settings stopped re-saving on every blur.** `SettingsEditor.would_change` compares
  coerced values, so `0.60` over a stored `0.6`, or a trailing blank line in a list, is
  correctly no edit. `set()` shares the coercion, so the two cannot disagree.
* **The chronicle panel is a share of the window** (floor 260, ceiling 520), applied
  on `page.on_resize`, with full filenames on hover.
* **AI actions grey out with an explanation** when no model is configured.
  `capabilities_for(settings)` reports `summarize`, `transcribe` and `normalize`; the
  desktop reads them from the *server* at startup, since in thin-client mode those are
  the server's extras and the server's model. An unreachable check leaves everything
  enabled rather than disabling the interface over a network hiccup.
* **Linking an external chronicle reads it.** `link_external_chronicle` creates and
  hydrates in one service call: speaker count, duration, status, transcript tag, and every
  speaker name into the workspace registry.
* **Bug found on the way: a linked chronicle's audio was invisible.**
  `sources_dir()` always pointed into the workspace while `chronicle_directory()`
  resolved the external path. `DatabaseManager.sources_path_for` is now the one answer
  for both.
* **`isolated_config` is a shared fixture.** It was duplicated, and its absence made
  a transcribe-dialog default depend on the developer's own config file.

1006 tests, 90% coverage; 976 + 2 skipped with the extras hidden; ruff and mypy clean.

### Sprint 9.1 — fixes from first real run (2026-09-03)

* **Alembic migrations are serialised process-wide.** `TranscriptView.did_mount`
  fires three concurrent panel loads, each opening a project session, and
  `_project_engine`'s cache check was separated from the migration by awaits - so all
  three missed the cache and all ran Alembic on the same file
  (`table audio_sources already exists`, `database is locked`). One lock covers *every*
  chain rather than one per database, because Alembic drives migrations through a
  process-global proxy and concurrent chains corrupt each other's context even on
  different files - which is the `KeyError: 'config'` in the same trace. Reproduced by a
  test that hung before the fix.
    * A database left half-migrated by the broken build needs recovery; see
      [docs/storage.md](docs/storage.md#migrations-are-serialised-process-wide).
* **PyAV is an explicit `normalization` extra.** It arrives free with
  `transcription`, but CI installs neither, so "zero new dependencies" was only true
  locally. Tests that decode real audio now skip via `pytest.importorskip("av")`, the
  same treatment faster-whisper gets, and a missing extra raises a `NormalizationError`
  naming the `pip install`. Verified green both with and without `av` present.
* **File dialogs report an actionable error.** A missing session bus surfaced as a
  raw `SocketException` against `/run/user/1000/bus`. Chronicler now recognises the
  missing-bus and missing-portal cases and names the fix. See
  [docs/troubleshooting.md](docs/troubleshooting.md).
* **Wizard defaults tests isolate config.** They read the developer's real
  `~/.config/Chronicler/settings.yaml`, so they passed or failed depending on the
  machine - the same class of bug Sprint 6 fixed for the config tests.

### Sprint 9 — normalisation, summarisation, recording, wizard (2026-09-03)

* **Identify speakers backfills the workspace registry**, not just the count.
* **German locale**, alongside English and Dutch, in the interface and as a
  transcription language.
* **Audio normalisation.** New `NORMALIZE` task on a PyAV `loudnorm` chain, zero new
  dependencies. Writes `<stem>.normalized.wav` beside the source and never touches the
  original. State, output filename and measured level are recorded per source. Verified on
  real under-gained audio: -39.5 -> -17.1 dBFS.
    * Available as a standalone action (hidden once a track is normalized) or via
      `normalize_first` on a transcribe task, which skips already-normalized sources.
    * **Transcription prefers the normalized copy** whenever a current one exists.
    * Reported level is RMS dBFS, not LUFS - PyAV exposes no way to read filter metadata,
      so ffmpeg's internal LUFS figure cannot be read back. `loudnorm` still targets LUFS.
      See [docs/audio-normalization.md](docs/audio-normalization.md).
* **LLM pipeline.** One `LlmClient` interface: OpenAI-compatible over httpx (covers
  llama.cpp-server, Ollama, LM Studio, vLLM, hosted gateways) and an optional in-process
  `llama_cpp` provider. `ModelRegistry` discovers models once at startup and caches them,
  falling back to the configured model when a server has no `/models` endpoint.
  *(Later replaced by `discover_models()` with no cache, which returns models and error
  together - ticket 023.)*
* **`SUMMARIZE` task.** Two-stage chunk-then-recap with real context budgeting.
  Summaries are **numbered and accumulate**, each recording its model, provider, prompt,
  chunk count and token usage - so several models can be compared on one transcript.
  Prompts are configurable per task with defaults in settings. New project-db table
  (migration `d4a81c62f9e5`).
* **Reading and browsing.** Summaries panel with read/delete, a full-transcript
  reader, and **Open the chronicle folder** in the native file manager - including the
  WSL2 `wslpath` translation.
* **Recording.** "Record a source" in a chronicle: device picker, start/stop, saved
  into the chronicle. Needs **no new RPC** - the microphone is client-side, so the
  recording goes through the existing `FileStager`, uploading in thin-client mode exactly
  as a picked file does.
* **Setup wizard.** Now asks language first (en/nl/de, applied to both interface and
  transcription) and offers an OS-aware workspace default under the user's Documents
  folder. A clean install writes every settings section with working defaults.
* **Character designer extracted** to `characterDesigner/` as a liftable subproject
  with its own `pyproject.toml`, no `chronicler` import, the 31-race table as data, a
  provider protocol, and a design document. Recommended name: **Dramatis**.
  *(Since moved out of this repository.)*

Fixed on the way: `TranscriptService.source_path` was sync, so `RemoteServiceProxy` never
exposed it and the Sources panel would have raised on a thin client - `AudioSource` now
carries its server-resolved path instead.

### Sprint 8 — parameters, subtitles, thin-client handshake (2026-09-03)

* **Transcription parameters.** `language`, `no_speech_threshold`, `model_size`,
  `device` and `compute_type` all resolve task payload -> settings -> field default.
  Nothing is hardcoded; `DEFAULT_MODEL_SIZE` is gone. `auto` is a real selectable value
  so a task can override a configured language. The model cache keys on
  (size, device, compute_type) rather than size alone.
    * Fixed on the way: the "install the transcription extra" guard wrapped an import
      that could never fail (faster-whisper is imported lazily inside `_get_model`), so
      the helpful message never appeared. It now wraps the call.
* **Settings are editable and persist.** `SettingsView` is a package with a Flet-free
  `SettingsEditor` doing validate-then-save against the tracked config file. Editable:
  UI locale, transcription language/model/threshold/normalise-first, the cleaning phrase
  list, match mode, repeat window and strip patterns, LLM provider/URL/key/model/path,
  and the workspace folder (the previously disabled picker now works). Per-section
  "restore defaults". Invalid input is rejected without touching the stored value.
* **Language picker offers the available locales plus `auto`**, built from a
  configurable `transcription.available_languages` merged with the UI locales.
* **SRT export.** Hand-written, no dependency. Refuses a text-imported transcript
  whose timings are synthetic line indices rather than seconds, instead of silently
  writing meaningless subtitles.
* **Workspace-wide speaker registry.** New archive table `known_speakers`
  (migration `c9f2a4e17b30`), case-insensitively deduplicated. The transcribe picker now
  offers every speaker used anywhere in the workspace, not just this chronicle's.
* **Thin-client handshake.** New `SystemService.get_server_info()` reports version,
  chronicle count and which optional extras the server actually has. On boot a thin
  client verifies the server is reachable, **requires an exact version match**, and pulls
  the chronicle list; a mismatch exits with a clear message instead of failing later.
* **Thin-client testing.** In-process integration tests drive a real
  `RemoteContainer` against the real server app (handshake, version mismatch,
  unreachable, wrong API key). `scripts/thin_client_check.py` runs a real server
  subprocess plus a real client and reports pass/fail. `--keep-running` leaves it up for
  another device; WSL2 `netsh portproxy` steps are documented.
* **`chronicler server --host/--port`**, needed for the LAN test and useful anyway.
* **`Container` resolves optional dependencies** (`T | None`), so a service can
  declare a dependency that is absent in some deployments.

### Sprint 7 — configurability foundation (2026-09-03)

Phases 01-04 of the post-prototype-salvage plan. See [docs/](docs/) for the reasoning
behind each; the code itself no longer carries explanatory comments.

* **Comment sweep.** All 618 inline comments and 199 multi-line docstrings moved
  into a new `docs/` tree (10 pages). Code keeps one-line docstrings and functional
  comments (`type: ignore`, `noqa`) only. 1,514 lines removed, no behaviour change.
* **Nested settings sections** — `transcription`, `cleaning`, `normalization`,
  `llm`, `ui` on `Settings`, all defaulted so existing config files keep loading.
  `CHRONICLER_TRANSCRIPTION__LANGUAGE=nl` works via `env_nested_delimiter`. An invalid
  section falls back to defaults with a warning instead of failing startup.
* **i18n** — `chronicler/i18n/` with nested message maps, `t("path.in.map")`,
  `{named}` interpolation, and an `nl` catalogue alongside `en`. Four integrity tests:
  no orphan keys, every leaf a string, placeholders matching across locales, and every
  literal `t()` call site in the package resolving against the English catalogue.
* **Configurable cleaning pipeline** — eight single-purpose rules, each switchable
  and parameterised, replacing the merge-and-normalise-only cleaner. Configurable
  hallucination phrase list with `exact` / `normalized` / `regex` matching, repeat-loop
  detection, duplicate-segment removal, strip patterns (ReDoS-guarded), minimum line
  length. `CLEAN` tasks accept a per-task override.
    * Measured on a real 2,816-turn prototype session: 650 junk turns removed (23%),
      of which 401 were repeat loops led by 232 `"Thank you."` hallucinations.
    * Defaults deliberately exclude `"Okay."`, `"Thank you."` and `"Bye."` — they are
      ordinary speech, and the repeat rule catches the looping case anyway. See
      [docs/cleaning.md](docs/cleaning.md).
* **Audio source records** — new `audio_sources` table in the project database
  (migration `b3c7e1d94a02`) carrying per-track transcription state, normalisation
  state, remembered speaker, and a content fingerprint. Filesystem owns existence, the
  database owns state; `list_audio_sources` reconciles them, so tracks copied in by
  hand are picked up with no import step. A deleted file is flagged `missing`, not
  dropped. Completion requires state `DONE` *and* a matching hash, so replacing a file
  re-offers the work. Closes the "no resumability" gap below.
* **Speaker quick-lookup** — the Sources panel shows per-track state and offers a
  searchable dropdown of known speakers with a free-text entry for a new one,
  pre-selected from the source record. Assigning a speaker is now its own action,
  separate from transcribing; transcribe only prompts when there is no speaker yet.
* `TaskType.NORMALIZE` and `TaskType.SUMMARIZE` reserved (handlers not built yet).

Everything else from the plan landed in Sprints 8 and 9.

### Sprint 6 — low-hanging fruit (2026-08-17)

Small items chosen for value per unit of effort; several turned out to be cheap because
the mechanism already existed and simply wasn't exposed.

* **Search actually searches.** Chronicle search covered the title only, so a
  chronicle tagged `product` or described as "roadmap" was unfindable by either word. Now
  title + description + tag names.
* **LIKE wildcards are escaped** in all three searching repositories. Typing `%`
  matched every row before.
* **Failed tasks can be retried from the UI** — the repository support was already
  written and tested, just unreachable. Two adjacent bugs fixed on the way: a returned-to-
  PENDING task kept the previous run's `claimed_by`/`claimed_at` (so the row showed a stale
  start time), and FAILED shared PENDING's icon (so a failure looked like a queued task).
* **Task rows name their chronicle**, and show their error inline instead of only
  recording it in the database.
* **Chronicle listings have a deterministic order** (`created_at DESC`, matching the
  task list). Without an `ORDER BY` the archive could reshuffle between two refreshes that
  changed nothing.
* **`page.bgcolor` and the sidebar divider follow the theme.**
* **`--config PATH` / `CHRONICLER_CONFIG_FILE`** for running an isolated instance.
* **Config tests no longer depend on the developer's machine.** They isolated
  `user_config_dir` but not `Path.home()`, so `Settings()` inside a test read the real
  `~/.chronicler_config.yaml` if one existed. This was masking a wrong assertion:
  `test_desktop_mode_requires_either` asserted that a thin client with no API key
  validates, which is false — it only passed because the real config supplied a key.

### Sprint 5 — structure and hygiene (2026-08-17)

* **No source file over ~370 lines.** `views/archive.py` (605) became a package
  (`view` / `cards` / `forms` / `imports`), `views/transcript.py` (372) became
  (`view` / `export` / `sources`), `processing/handlers.py` (332) became one module per
  task type over a shared `HandlerBase`. *(2026-11-10: no longer holds.
  `views/transcript/view.py` is 599 lines.)*
* **Import logic lifted out of the view.** `ImportCoordinator` decides what an audio
  or transcript import does to the workspace, with no Flet dependency — so it's testable
  without a page attached, and `ArchiveView` is left with layout plus event plumbing.
* **One dialog primitive.** The await-a-dialog-choice boilerplate was copy-pasted
  three times across two views; it's now `chronicler/desktop/dialogs.py`
  (`ask_choice` / `confirm` / `ask_text`).
* **Worker wiring shared between entry points.** `core/worker_wiring.py` — a handler
  registered in only one of desktop/server was a task type that silently never ran in the
  other.
* **mypy gates the whole package.** The `ignore_errors` override for
  `desktop/app.py`, `components/sidebar.py` and `views/archive.py` is gone; the two real
  Flet-API type errors behind it are fixed.
* **Tests mirror the package tree** (`tests/chronicler/core/processing/handlers/…`,
  `tests/chronicler/desktop/views/archive/…`), the four copy-pasted `async_session`
  fixtures are one shared fixture, and fixture-file paths are anchored in
  `tests/paths.py` instead of `parents[n]`. Coverage 90% (CI floor 80%).
* **Dead code removed.** `perform_test_task` moved out of production into the test
  that uses it; `RpcServer.register`/`_service_classes` double bookkeeping collapsed;
  `SettingsView.setting_card`'s seven colour parameters replaced by the palette it
  already had.
* **`SearchService` is no longer five stubs.** The three methods backed by existing,
  tested repository queries (`search_chronicle_meta`, `search_tags`, `search_tasks`)
  are implemented; the two that genuinely need new infrastructure now say so and why
  *(Later deleted outright, in Sprint 11.)*
* **`themeMockup/` retired.** It was a fork of Flet's `declarative_trolli` gallery
  example, so half of it (`components/`, the Pacifico font) was another app's code
  entirely. The Chronicler-specific parts have all been applied — see
  [the theme mockup](#the-theme-mockup) below. The remaining gaps are in
  [ROADMAP.md](ROADMAP.md).

#### The theme mockup

`themeMockup/` (added 2026-07-29, removed 2026-08-17) was a static Flet mockup of the
desktop UI. Its structure, copy and layout **are** what shipped: the sidebar
(CHRONICLER wordmark, "Preserve conversations.", the same three nav entries, the
workspace footer), the chronicle card (kind/status header row, title, 2-line
description, date/duration/speakers row, tag line), the task rows, the settings cards
(Appearance / Workspace / Connection), and the transcript view's two-panel split with
its right-hand Chronicle detail panel. The real views have since gone further than the
mockup in every case.

* **`page.bgcolor` is never set.** Fixed 2026-08-17: `DesktopApp._apply_theme` is now
  the one place that paints everything the app owns directly (page background, content
  area, and the sidebar/content divider — which was coloured once at construction and
  never updated on a theme change).

### Sprints 1-4 — from prototype to the core loop (2026-08-13)

Sprint 4 delivered Chronicle CRUD, audio import, faster-whisper `TRANSCRIBE` and
plain-text export, plus four rounds of UI fixes found by running the app; those are in
[Notes by area](#notes-by-area).

#### Sprint 1

* **Server mode cannot start.** `SQLiteTagRepository.search` implemented; server-build
  smoke test added (`tests/chronicler/core/test_server_main.py`).
* **Web client leaks the API key.** Web client is now a true reverse proxy
  (`POST /api/{service}/{method}`, `POST /api/upload`); `GET /config` no longer returns
  `api_key`. Also fixed alongside: CORS `allow_credentials` was `True` with a wildcard
  origin (invalid/unsafe combo), API key comparison now uses `secrets.compare_digest`.
* **Path traversal in `/upload`.** On-disk filenames are now server-generated
  (`uuid4()` + whitelisted extension); a 500MB size cap is enforced with cleanup of
  partial files; `python-multipart` moved into `requirements.txt`.
* **Import tasks trust client input.** `file_path` is confined to the imports
  directory in `handle_import` (`is_relative_to` check). User patterns are compiled with
  the `regex` package, capped at 500 characters, and every match has a timeout
  (`chronicler/core/processing/regex_guard.py`).
* **CI gates nothing.** `continue-on-error` removed from ruff/mypy; flake8 dropped
  (100% overlap with ruff, confirmed by running both); `--cov-fail-under` added.

#### Sprint 2

* **One `AsyncSession` shared everywhere.** UI, worker loop and every HTTP request used
  to share a single session — real crash risk (`IllegalStateChangeError`) under any
  concurrent use. `RpcServer` now resolves a fresh `Container` scope per request
  (`Container.create_scope()`); `DesktopApp`'s `WorkerManager` gets its own dedicated
  session, never touched by the UI, and `update_view()` opens a fresh session per
  navigation instead of holding one for the app's lifetime. Verified live: 30 concurrent
  requests against a real server, no errors.

Known limitation, accepted rather than fixed:

* **No upgrade path from a pre-Alembic workspace.** Adopting Alembic (see Schema management under Notes by area) means any
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

#### Sprint 3

Found by an actual live smoke test (a real running
`chronicler server`, driven over genuine HTTP — not `ASGITransport`, not mocks) that
every `ASGITransport`-based test in the sprint had missed:

* **Thin Client mode was a `sys.exit(1)` stub.** `DesktopApp` now resolves services
  through `Container` (full-stack) or `RemoteContainer` (thin client) via
  `chronicler/desktop/runtime.py::build_runtime`, chosen from `Settings.mode`. Includes
  transcript viewing (`TranscriptService` redesigned to be project-scoped and reachable
  over RPC) and file import (`FileStager`: copy locally, upload via `/upload` remotely).
* **`RemoteServiceProxy` couldn't serialize `UUID` arguments at all.** Every argument is
  now serialized via `TypeAdapter(declared_param_type)` keyed off the method's real type
  hints, not guessed from the runtime value. `chronicle_id: UUID` is the single most common
  argument shape in this codebase; this silently broke almost any real remote call.
* **`RpcServer._add_route` made every optional parameter mandatory over RPC.** It wrapped
  every parameter as `Body(..., ...)` unconditionally (Ellipsis = required in FastAPI),
  discarding the method's own default. Omitting an optional argument, or explicitly
  sending `null` for one, both 422'd — including from the desktop app's own existing
  calls (e.g. `create_chronicle` with only some optional kwargs set), the moment they ran
  in thin-client mode. Now preserves the method's actual default.
* **`TaskService.queue_import`/`queue_clean` had no return type annotation** — silently
  returned a raw `dict` instead of a `Task` to any `RemoteContainer` caller. Added `-> Task`
  to both.

## Notes by area

The old `TODO.md` also tracked features by phase, with notes written as each landed.
These are the done items and their notes, as they were. Open items moved to
[ROADMAP.md](ROADMAP.md).

### Project foundation

* Create repository structure
* Configure Python package
* Add development dependencies
* Add formatting tools
* Add linting

### Application foundation

#### Configuration

* Create application settings system
* Store user configuration in OS config directory
* Create first-run wizard
* Select workspace location
* Validate workspace permissions — opening a workspace writes a probe file and reports
  an unwritable folder on the startup screen, and both setup wizards refuse an existing
  folder that cannot be written to (ticket 055)
* Automatic configuration validation for different run modes
    * `Settings.mode` added 2026-08-13, set by `ConfigWizard` at every point it already
      knows which of the four concrete setups was chosen — "the active mode is
      determined by the configuration" is now true.
* Point Chronicler at a specific config file (2026-08-17). `chronicler --config PATH`
  or `CHRONICLER_CONFIG_FILE`; `Settings.save()` writes back to the same place. A file that
  was explicitly requested but doesn't exist resolves to *no* config rather than falling
  through to the defaults - silently loading the developer's real config would defeat the
  point and, in a smoke test, point a throwaway run at their real workspace.
* Use argparse for command-line arguments and --verbose mode
* Persist the deployment mode in settings
* Stop generating an API key when the user leaves it blank in thin-client setup
    * Fixed 2026-08-13: `RemoteServerStep` now re-prompts with an explanation instead of
      generating a key that can't possibly match the server's.
* Surface config parse errors instead of swallowing them (`except: pass` in `config.py`)
    * Fixed 2026-08-13: logs a warning naming the broken file; falls back to defaults
      the same way it did before (behavior-preserving, just no longer silent).

#### Architecture alignment

* Implement DI container for service resolution
* Refactor DesktopApp to use DI container
    * Done 2026-08-13. `chronicler/desktop/runtime.py::build_runtime` builds a
      `Container` (full-stack) or `RemoteContainer` (thin client) from `Settings.mode`;
      `DesktopApp.update_view()` resolves services through it instead of constructing
      repositories by hand.
* Support switching between local and remote services based on settings
    * Same mechanism as above — `build_runtime` is the switch.

#### Backend abstraction

* Define repository interfaces
* Separate services from storage
* Create local storage backend
    * Transcript search is `SQLiteTranscriptRepository.search`, over an FTS5 index in each
      chronicle (ticket 063, docs/search.md).
* `DatabaseManager._project_engines` cached a pooled engine per chronicle forever,
  holding a thread and an open file each. Project engines now use `NullPool`, so the
  cache holds no connection.
* Prepare remote API backend interface — `RemoteContainer` / `RemoteServiceProxy`, tested

The goal: the UI and services should not depend directly on SQLite.

### Chronicle storage

#### Archive database

* Projects/Chronicles table
* Tags table
* Persistent task table
* Task claim columns (`claimed_by`, `claimed_at`) and `attempts` / `max_attempts`
    * Added 2026-08-13 along with `SQLiteTaskRepository.claim_next()`, an atomic claim.

#### Chronicle database

* Speakers
* Transcript lines, each recording the audio source it came from (ticket 010)
* Audio sources, with their transcription and normalization state (Sprint 7)
* AI analysis results — numbered summaries (Sprint 9)

#### Schema management

* Replace `DatabaseManager._migrate_schema_sync` with Alembic
    * Done 2026-08-13. Two independent chains (`chronicler/migrations/archive`,
      `chronicler/migrations/project`), invoked programmatically (no static
      `alembic.ini` - the project chain runs against a different file per chronicle).
      Known limitation: no upgrade path from a pre-Alembic workspace - see Sprint 2
      above.
* Baseline migration for the archive database
* Baseline migration for the project database

### Worker framework

* Create worker manager
* Create worker lifecycle
* Persistent task handling (store tasks in master database)
* **Task claiming**
    * Fixed 2026-08-13: `SQLiteTaskRepository.claim_next(worker_id)` does a conditional
      `UPDATE ... WHERE status='PENDING'` + rowcount check - atomic, safe under
      concurrent callers (two processes against one workspace no longer double-run a
      task).
* Task status tracking: WORKING, DONE, FAILED
    * `WAITING` removed 2026-08-13 - confirmed unused anywhere in the codebase.
* Task progress tracking
* Error handling
* **Retry support**
    * Fixed 2026-08-13: `attempts`/`max_attempts` columns, `mark_failed_or_retry()`
      resets a task to PENDING (below max_attempts) instead of FAILED.
      `WorkerManager.process_tasks()` bounds each poll cycle to what was pending when
      the cycle started, so retries spread across poll cycles rather than all firing
      instantly in one burst.
    * Since the audit: a failed task waits 30 seconds, then 5 minutes, before it can be
      claimed again (ticket 022); tasks found WORKING at start are recovered (009); each
      step uses its own short session (007).
* Run a worker manager in server mode
    * Fixed 2026-08-13: `server/main.py` builds a `WorkerManager` and runs it alongside
      `uvicorn.Server(...).serve()` via `asyncio.gather()`. Verified live: a queued task
      went PENDING -> DONE on a real server with no client polling it.
    * Consolidated 2026-08-17: both entry points now call
      `core/worker_wiring.py::build_worker_runtime`, so a newly added handler can't be
      registered in one mode and silently missing in the other (which is exactly how
      TRANSCRIBE nearly shipped desktop-only).

Initial tasks:

* IMPORT — formatted text. Audio no longer takes this path at all: an audio import
  is stored as a source and transcribed via TRANSCRIBE, which is what it was previously
  guaranteed to fail at (UTF-8 decode on a binary file).
* TRANSCRIBE — faster-whisper, one audio source at a time, with the speaker assigned
  by the user. No diarization: one source is treated as one speaker's track. The model is
  downloaded lazily on first real use, and the optional `transcription` extra being absent
  produces an explanatory error rather than a crash.
* CLEAN
* NORMALIZE (Sprint 9)
* SUMMARIZE (Sprint 9)
* EXPORT — not a task: exports are service calls, run off the event loop (ticket 028)

* AI_SUMMARIZE, planned as a future task, shipped as SUMMARIZE (Sprint 9)

### Desktop application

#### UI

* Application shell
* Navigation
* Theme support
    * Fixed 2026-08-13: `Settings.dark_mode` persisted; startup respects it (was
      hardcoded `ft.ThemeMode.DARK`); the Settings toggle actually updates
      `page.theme_mode` and saves.
    * Extended 2026-08-13 (Sprint 4 UI fixes): that first fix only flipped
      `page.theme_mode`, which every *unstyled* Flet control follows automatically —
      but ArchiveView, TasksView and `DesktopApp.content_area` all hardcoded
      `BLUE_GREY_800/700` backgrounds regardless of theme (only SettingsView and
      TranscriptView's own inline ternaries were theme-aware, and TranscriptView's
      `dark_mode` param was never actually passed a real value from `app.py`). Toggling
      to light mode left cards/content area exactly as dark as before, with
      default-adaptive text/icons now landing on the wrong side of the contrast for a
      still-dark surface — the "light text on light background" symptom. Extracted the
      already-correct settings.py palette into `chronicler/desktop/theme.py`
      (`theme_colors(dark_mode) -> ThemeColors`), applied it in all four views plus
      `content_area`, and made `on_dark_mode_change` rebuild the current view (colors
      are baked in at construction) instead of only flipping `page.theme_mode`.
    * Extended again 2026-08-13 (found in live use after the above): the sidebar
      (`components/sidebar.py`) was still hardcoded `BLUE_GREY_900` and never
      considered `dark_mode` at all, and three spots used a bare `ft.Colors.AMBER_300`
      accent for status text/icons (TranscriptView's "Imported" badge, SettingsView's
      connection badge, TasksView's WORKING icon) — bright enough to read on dark
      surfaces but low-contrast on the new light-mode `WHITE` ones. Added `accent` and
      `sidebar` to `ThemeColors` (`AMBER_300`/`BLUE_GREY_900` dark,
      `AMBER_800`/`AMBER_50` light); `Sidebar` takes `dark_mode` at construction and
      gained `set_dark_mode()` since - unlike the content views - it's built once in
      `main()` and never naturally rebuilt on navigation, so `on_dark_mode_change`
      calls it explicitly.
    * Extended a third time 2026-08-13 (still wrong in live use): the light-mode
      `sidebar`/`border` picks from the previous fix were themselves bad choices -
      `AMBER_50` sidebar read as an odd yellow/brown tint next to the rest of the now
      pure-white light theme instead of a deliberate accent, and `AMBER_100` borders
      are a near-white pale yellow, practically invisible against a white surface.
      `sidebar` is now the same `WHITE` as `surface` (matches the rest of the app, as
      asked, rather than introducing its own tint); `border` is `BROWN_200` - keeps
      the app's warm palette but is actually visible.
* Fix "Unknown control: FilePicker" client error
    * Fixed 2026-08-13 (found in live use): `ft.FilePicker` is a `Service`
      (`flet.controls.services.service.Service`), not a visual control - adding it to
      `page.overlay` (which expects renderable widgets, same list `AlertDialog`/
      `SnackBar` use) makes the client fail outright with "Unknown control:
      FilePicker" the moment that view mounts. Services register through
      `page.services` instead. `TranscriptView` did this wrong outright (visible
      crash); `ArchiveView` never registered its `file_picker` *anywhere* (a
      pre-existing latent bug this also fixed) - both now use `page.services`.

#### Archive view

* Browse Chronicles
* Implement search in repositories and services
    * Workspace search — chronicle title, description and tag names (`ILIKE`), with
      the user's own `%` and `_` escaped, and a chronicle with two matching tags listed
      once.
    * Transcript search, within a chronicle and across the workspace (ticket 063)
    * `SearchService` was deleted in Sprint 11: no view used it, and both search boxes
      call the owning services directly.
* Search UI in Archive view
* Open Chronicle
* Import Transcript (via Header)
* Edit Chronicle metadata (title/description/kind/duration)
    * Added 2026-08-13 (Sprint 4 UI fixes): `ChronicleService.update_chronicle` already
      worked end-to-end, there was just no UI calling it anywhere. Per-card "Edit"
      button opens a dialog pre-filled from the Chronicle, saves via the existing
      service method.
* Delete Chronicle
    * Fixed 2026-08-13: `ChronicleService.delete_chronicle` worked but had no UI and
      no cascade (`DBTask.chronicle_id` and `chronicle_tags` have no
      `ondelete=CASCADE`, and SQLite doesn't enforce FKs by default here anyway - see
      `database.py`). `SQLiteChronicleRepository.delete()` now cleans up `DBTask` rows
      and `chronicle_tags` associations in the same transaction as the chronicle row.
      `ChronicleService` gained a `DatabaseManager` dependency (auto-wired by
      `Container` the same way `TranscriptService` already gets it) so it can also
      remove the on-disk `chronicles/<id>/` directory - but only for a chronicle whose
      data actually lives there (`project_path` unset); a linked chronicle's
      externally-located `project.db` is never touched. Per-card "Delete" button asks
      for confirmation via `page.show_dialog()`/`pop_dialog()` (the correct pattern -
      see the overwrite/append dialog's regression note under Import below for why the earlier
      raw-`page.overlay` approach silently failed to close).
* Consistent header button styling
    * Fixed 2026-08-13: "New Chronicle" (`ElevatedButton`) and "Import" (a manually
      styled `Container`, since `PopupMenuButton` needs a custom `content` to look like
      a button) had different padding/shape/elevation. Gave `ElevatedButton` a matching
      `ButtonStyle` (radius 8, same padding, `elevation=0`) so they read as one style.
    * Superseded 2026-08-13 (still didn't actually look identical in live use -
      `ElevatedButton` carries its own Material minimum-tap-target/ink/icon-gap
      defaults that `style=` can't fully cancel out): replaced `ElevatedButton`
      entirely with the same manually-styled `Container` pattern "Import" already
      used, extracted into one shared builder, `chronicler/desktop/widgets.py::
      amber_button()`. Both buttons now go through the identical code path, so they're
      guaranteed pixel-identical rather than independently tuned to look close. Also
      used for the transcript view's "Export" button. Bonus: drops the
      `ElevatedButton` deprecation warning (deprecated since Flet 0.80, removed in 1.0).
* Dropdown affordance on menu-opening buttons
    * Added 2026-08-13: "Import" and "Export" open a `PopupMenuButton` menu but looked
      identical to a plain action button, no visual hint they'd expand. `amber_button()`
      takes a `dropdown=True` flag that appends a thin separator + a small
      `EXPAND_MORE` chevron after the label.
* Fix un-awaited coroutines in card action callbacks (`clean_clicked`, per-card imports)
    * Fixed 2026-08-13 (Sprint 4 item 0): Flet's dispatcher only awaits a handler when
      `inspect.iscoroutinefunction(handler)` is true of the object assigned to
      `on_click` itself — a `lambda e, i=x: self.async_method(e, i)` fails that check,
      so the coroutine it returns was created and silently dropped. Per-card controls
      now bind the bound async method directly and carry the chronicle id via `data`
      (read back as `e.control.data`) instead of a lambda closure. Regression test:
      `test_card_action_controls_bind_async_handlers_directly` asserts
      `inspect.iscoroutinefunction` on every per-card `on_click` — the same predicate
      Flet uses — so this class of bug fails CI instead of surviving unnoticed again.
* Fix snackbars — `page.snack_bar = ...` is the pre-0.70 Flet API and no longer displays
    * Fixed 2026-08-13 (Sprint 4 item 0): `ArchiveView.show_snackbar` now calls
      `page.show_dialog(ft.SnackBar(...))`, verified against the installed flet 0.86.4
      API (`ft.Page` has no `snack_bar` attribute at all). Regression test:
      `test_show_snackbar_uses_page_show_dialog` uses a `spec=ft.Page` mock, so it fails
      if `show_dialog` is ever renamed/removed again.

#### Create Chronicle wizard

* Select files
* Create Chronicle (Basic implementation)

#### Task monitor

* View active tasks
* Retry failures
    * Added 2026-08-17. The mechanism already existed and was tested - `update_status(id,
      PENDING)` clears the error and resets progress - it was simply never exposed.
      `TaskService.retry_task` plus a retry button on finished rows. One click buys one
      attempt: `attempts` is deliberately *not* reset, because the automatic budget is
      already spent by the time a task reaches FAILED and refilling it would make a
      deterministic failure (bad regex, missing file) fail three more times per click.
      `update_status` now also clears `claimed_by`/`claimed_at` on the return to PENDING,
      which it should always have done - the row kept showing the previous run's start
      time until something claimed it again.
* Show which Chronicle each task belongs to (2026-08-17)
* Hide completed tasks by default
    * Fixed 2026-08-13: the "Hide completed tasks" checkbox existed but defaulted to
      unchecked, so a growing pile of DONE tasks was the first thing shown. Now
      defaults to `True`.
* Order tasks newest first; show started/completed timestamps
    * Fixed 2026-08-13: `get_all()`/`search()` had no `ORDER BY` at all (whatever order
      SQLite happened to return). Added `ORDER BY created_at DESC`. No schema change
      needed for the timestamps either - `claimed_at` (set by `claim_next()`) is
      "started", and `updated_at` (bumped by `onupdate=datetime.now` on every write,
      including the final `update_status(..., DONE)`) is "completed" once the task
      reaches a terminal state. Each task row now shows Created/Started/Completed.
* More task logging
    * Fixed 2026-08-13 (reported: "I only see the transcript started, not finished or
      intermediate states"): `WorkerManager._execute_task` now logs the claim, every
      `update_progress()` call, and completion generically for every task type,
      instead of relying on each handler to log its own bookends. `handle_import`/
      `handle_clean` additionally log line/speaker counts at parse and finish, so a
      real import's log trail now reads claim → parsed N lines → progress 50% →
      finished: N lines, M speakers → completed, not just the one start line.
* Live refresh on task completion (desktop mode)
    * Added 2026-08-13 (reported: "the chronicle does not update when a task
      finishes"): `chronicler/core/task_events.py` adds `TaskEventBus` - a small
      in-process publish/subscribe. `WorkerManager` takes an optional `event_bus` and
      publishes a `TaskCompletedEvent` once a task reaches a terminal state (DONE, or
      FAILED with no retries left - a retry that goes back to PENDING does *not*
      publish one, since nothing's "completed" yet). `DesktopApp` is the only current
      subscriber: full-stack desktop mode is the one case where the WorkerManager and
      the UI genuinely share a process/event loop, so a live refresh is actually
      achievable - `_on_task_completed` calls `update_view()` to refresh whatever's
      on screen (skipping Settings, and skipping the transcript view if the finished
      task belongs to a *different* chronicle than the one being viewed). Also fixed
      along the way: `update_view()`'s TRANSCRIPT branch used to reuse
      `state.selected_chronicle` as-is (a snapshot from whenever the user navigated
      there) - `TranscriptView` bakes speakers_count/duration/status/tags into its UI
      at construction time from whatever `Chronicle` it's given, so without a
      re-fetch the refresh would rebuild the view with the same stale data. Now
      re-fetches by id on every `update_view()` call (going back to the archive list
      if the chronicle was deleted out from under an open view).
    * Since ticket 027 the view on screen refreshes in place rather than being rebuilt.
    * Explicitly *not* built: any transport for thin-client/web. `TaskEventBus`'s
      `subscribe()`/`publish()` shape is deliberately transport-agnostic - a future
      websocket/SSE-backed implementation could plug into `WorkerManager` the same
      way `DesktopApp`'s does - but today's RPC (`RemoteServiceProxy`) is
      request/response only, with no server-push mechanism to build that on. Server
      mode's `WorkerManager` (`server/main.py`) doesn't get an `event_bus` yet since
      nothing would consume the events.
    * Follow-up planned 2026-08-13, not yet implemented: **Server-Sent Events**,
      decided over WebSocket - see [docs/live-updates.md](docs/live-updates.md) for the
      analysis and the server and thin-client design.

#### Settings view

* Replace the static mock with real settings
    * Fixed 2026-08-13: workspace path/connection mode/theme all reflect real
      `Settings`. Editing settings from within the running app is still out of scope
      (connection mode isn't switchable at runtime).
* Edit settings in the app (Sprint 8): language, transcription, cleaning, language
  model and workspace folder, validated before anything is saved. The connection mode is
  still not switchable at runtime, and a new workspace folder applies after a restart.

### Processing

#### Import

* Audio importer — audio is stored as one of a chronicle's sources, then transcribed
  (Sprint 4). Recording in the app adds one too (Sprint 9)
* Import worker
* Regex importer
* Confine import paths to the workspace
    * Fixed 2026-08-13: enforced in `handle_import` (resolve + `is_relative_to` against
      the imports directory), at the point of file access, so it covers any caller.
* Bound regex execution (ReDoS)
    * Replaced the static pre-filter with the `regex` package: patterns over 500 chars
      are rejected, and every match has a timeout and releases the GIL, so a slow
      pattern fails its task and the event loop keeps running.
* Overwrite/append confirmation
    * Fixed 2026-08-13 (Sprint 4 UI fixes): `handle_import` unconditionally called
      `delete_all_lines()` before writing the new file's lines — importing a second
      transcript into a chronicle that already had one silently destroyed it, no
      warning. `TaskService.queue_import`/`handle_import` gained an `append: bool`
      flag (skips the delete; offsets the new lines' `start_time` past the existing
      max instead). Fixed a related latent bug in the process: `RegexImporter` gave
      every line `start_time=0.0`, so `get_lines()`'s `ORDER BY start_time` had no real
      tiebreaker for text imports — it "worked" only by accident of SQLite's scan
      order. Now assigns sequential per-file indices, so append has a real offset to
      build on and ordering is deterministic. `ArchiveView` checks for an existing
      transcript before importing into a chronicle and asks Overwrite/Append/Cancel.
    * Fixed 2026-08-13 (found in live use): the confirmation dialog's buttons worked
      (the future resolved, the import proceeded correctly) but the dialog itself
      never visually closed. Root cause: `_ask_overwrite_or_append` built the dialog
      by hand (`page.overlay.append(dialog)`, `dialog.open = True/False`,
      `page.update()`) and removed it from `page.overlay` immediately after setting
      `open = False` - `AlertDialog`'s close is animated client-side, and Flet's own
      `BasePage._wrap_dialog_on_dismiss` comment says removing a dialog before the
      client confirms the animation finished "can drop the post-animation dismiss
      callback entirely." Switched to `page.show_dialog()`/`page.pop_dialog()`, which
      wrap `on_dismiss` and only remove the dialog once the client actually reports
      it closed. `create_dialog`/`transcript_dialog`/`edit_dialog` in this same file
      use the older raw-`page.overlay` pattern too, but as *persistent* dialogs (added
      once, never removed, only `open` toggles) rather than a fresh instance per call
      - not hit by this specific bug, but the same underlying risk if that ever
      changes; worth a look if any of them are ever reported not closing.
* Tag imported chronicles + backfill speaker count
    * Fixed 2026-08-13 (Sprint 4 UI fixes): two dead-data-model items reopened in the
      2026-08-13 re-baseline are now live for the import/clean path specifically.
      `handle_import` already built a full `speaker_map` as a side effect of parsing —
      it just never wrote it anywhere. Now backfills `Chronicle.speakers_count` after
      every import/clean (counting distinct speaker names across every line
      currently in the transcript, not just the just-parsed ones — matters for append
      mode) and tags the chronicle `"Transcript"` via the new
      `ChronicleRepository.add_tag` (get-or-create by name, since `DBTag.name` is
      unique; idempotent). A manual "Identify Speakers" per-card action
      (`TranscriptService.refresh_speaker_count`) covers reconciling chronicles
      imported before this existed, or hand-edited since. `chronicle_tags` and
      `speakers_count` are no longer fully dead — see the still-open items below for
      what's left (tag *creation*/*management* UI, tags beyond "Transcript").
* Import transcript with timestamps
    * Added 2026-08-13: `RegexImporter` takes an optional `timestamp_group` - when
      given, that capture group is parsed (`chronicler/core/formatting.py::
      parse_timestamp`, accepts `H:MM:SS`/`HH:MM:SS`/`MM:SS` and an optional
      fractional-seconds suffix) into the line's real `start_time`, instead of the
      synthetic per-line index used when no timestamp is captured. `end_time` is
      derived from the *next* line's `start_time` (only a start is captured per
      cue); the last line is zero-length rather than guessing. `TaskService.
      queue_import`/`handle_import` thread `timestamp_group` through; `ArchiveView`'s
      Import Transcript dialog gained a "Timestamp Group Index (optional)" field.
      `DefaultImporter` (the no-regex-specified path) has no timestamp support - a
      fixed pattern with no timestamp group in it, by definition; timestamped import
      is only available via a user-supplied regex. Append mode's existing offset
      logic (shift new lines past the current max `end_time`) needed no changes -
      "this content comes after what's already there" is the same operation whether
      the shifted values are synthetic indices or real seconds.

#### Transcription

* Whisper integration
    * Added 2026-08-13 (Sprint 4 close-out): `chronicler/core/processing/transcriber.py`
      wraps `faster_whisper.WhisperModel`. `WhisperModel` is only constructed inside
      `_get_model()`, called only from `transcribe_audio()`, called only from
      `WorkerHandlers.handle_transcribe` when a TRANSCRIBE task actually runs - nothing
      at module import or app-startup time touches it, so the (~150MB, `"base"` size)
      model only downloads on first real transcription, not on every app launch.
      Loaded models are cached by size so a second task doesn't reload/redownload.
      `model_size` isn't a `Settings` field yet (hardcoded `DEFAULT_MODEL_SIZE =
      "base"` in `transcriber.py`) - nobody's asked to tune it; trivial to add if
      needed later.
* Transcription worker
    * `WorkerHandlers.handle_transcribe` registered in both `desktop/app.py` and
      `server/main.py` alongside IMPORT/CLEAN. `transcribe_audio()` is synchronous and
      CPU-bound (real transcription can take minutes) - run via `asyncio.to_thread()`
      so it doesn't block the event loop the desktop UI shares with the worker loop in
      full-stack mode. A missing `transcription` extra raises a clear failed-task
      message (`RuntimeError` with the `pip install` hint) instead of crashing the
      whole worker loop.
* Timestamp handling — faster-whisper's segment `start`/`end` (real seconds) are
  used directly as `TranscriptLine.start_time`/`end_time`, giving `get_lines()`'s
  `ORDER BY start_time` real, meaningful values for once (text imports only ever had
  synthetic per-line indices - see the append/overwrite entry above).
* Real audio import
    * Fixed 2026-08-13: `ArchiveView`'s "Import Audio" used to call
      `TaskService.queue_import()` (the text path, which opened the audio file as
      UTF-8 and failed every time) or, briefly mid-Sprint-4, immediately queued a
      transcription. Redesigned 2026-08-13 (see the multi-track item below) so
      importing an audio source and transcribing it are two separate, explicit
      actions: `ChronicleService.add_audio_source()` just moves the staged file into
      a durable `chronicles/<id>/sources/` and returns - no task, no transcription -
      so a user can gather every track for a session before transcribing any of them.
* Multi-track / per-speaker transcription
    * Redesigned 2026-08-13 after real usage clarified the actual recording setup:
      each "chronicle" (podcast episode) is recorded as *separate single-speaker
      audio tracks* (one per Discord participant, via a per-user recording bot) plus
      a separate music track - not one multi-speaker file. `TaskType.TRANSCRIBE` now
      requires a `speaker_name` (`TaskService.queue_transcribe(chronicle_id,
      file_path, speaker_name)`) - transcribing one track is explicitly "this whole
      track is speaker X". `handle_transcribe` only deletes *that speaker's* existing
      lines (`TranscriptRepository.delete_lines_by_speaker`) before inserting the new
      ones, so re-transcribing (or transcribing) one participant's track never
      touches another's already-transcribed lines. Segment timestamps are used
      as-is, not offset: separate per-participant tracks from the same Discord
      session are already time-aligned on a shared timeline, so sorting the combined
      transcript by `start_time` interleaves speakers correctly for free. The
      transcript view gained a "Sources" panel (`TranscriptService.list_audio_sources`
      lists the sources/ directory) - each track has a "Transcribe" action that asks
      which speaker it is (existing speaker names shown as a hint;
      `get_or_create_speaker` matches by exact name, so typing one exactly reuses
      that speaker rather than creating a near-duplicate).
    * Explicitly out of scope for now (the user's own words): real diarization
      (multiple speakers auto-identified within one track) - every source is assumed
      single-speaker. The music track mentioned as part of the recording setup isn't
      given any special handling either - it's just not one anyone would click
      "Transcribe" on; mixing tracks into one podcast file is a distinct, larger,
      not-yet-scoped feature.
* Chronicle duration and status backfill
    * Fixed 2026-08-13 (reported: "after transcribing the duration is not updated";
      "the state of the chronicle should not be [stuck at] 'Imported' after audio
      transcription"): `Chronicle.duration` was never computed anywhere - always
      "Unknown duration". `handle_transcribe` now backfills it from the *whole*
      transcript's longest line (`max(end_time)` across every speaker's track, not
      just the one just transcribed - two participants' tracks can run different
      lengths), formatted via the new `chronicler/core/formatting.py::format_duration`
      ("1h 24m"). Text imports/cleans still don't touch `duration` - their
      `start_time`/`end_time` are synthetic per-line indices, not real time, and
      would produce a meaningless value. `status` also defaults to "Imported" and is
      never otherwise updated - `handle_transcribe` now sets it to "Transcribed", but
      only if it's still the untouched default (won't stomp a chronicle whose status
      was already something else on purpose).

#### Cleanup

* Cleanup worker
* Text normalization
* Segment merging
* Confirm before cleaning, and snapshot the database first (ticket 011)
* Make import/clean transactional
    * Fixed 2026-08-13: repository methods no longer commit internally; `handle_import`/
      `handle_clean` commit once at the end, rollback + re-raise on any exception.
* Stop recreating speaker rows on every clean (speaker IDs change each run)
    * Fixed 2026-08-13: `delete_all()` renamed to `delete_all_lines()` and no longer
      touches `DBSpeaker` - `get_or_create_speaker()`'s lookup-by-name now naturally
      reuses the same row across re-imports/cleans.

### Editing and export

#### Transcript viewer

* Display transcript
* Show line timestamps (optional)
    * Added 2026-08-13: a "Show timestamps" checkbox in the transcript panel prefixes
      each line with `[HH:MM:SS]` (`chronicler/core/formatting.py::format_timestamp`,
      the same helper used by timestamped export, so the two always agree). Toggling
      reformats the already-fetched lines in place rather than re-querying the
      transcript, so it doesn't flash "Loading..." or cost a round trip. No
      distinction is made between "real" timestamps (from whisper) and the synthetic
      per-line indices text import uses when no `timestamp_group` is given - the
      checkbox shows whatever `start_time` actually holds either way; a text-imported
      chronicle without real timestamps will show small ascending values
      (`00:00:00`, `00:00:01`, ...), not a claim of precision that isn't there, but
      also not hidden behind a "is this real" flag that doesn't exist in the schema.
* **Edit text** — done in Sprint 11, per line rather than as one blob. The read view
  stays read-only on purpose; the edit toggle swaps in one row per line. See
  [docs/transcript-editing.md](docs/transcript-editing.md).
* Search within Chronicle (ticket 063)

#### Export

Initial:

* Plain text export
    * Added 2026-08-13 (Sprint 4 UI fixes): `TranscriptService.export_plaintext`
      wraps each line at 140 columns with a hanging indent under `"Speaker: "` (width
      varies per speaker name), dropping lines with no real text. Verified against a
      real fixture, not just hand-written expectations:
      `test_export_plaintext_matches_cleaned_example_after_import_and_clean` imports
      `examples/example_transcript_001.txt`, runs Clean, exports, and asserts the
      result is byte-for-byte identical to `examples/example_transcript_001_cleaned.txt`
      (which predates this code — a genuine format-compatibility check).
    * Corrected 2026-08-13 (real exported output didn't match what was actually
      wanted, once seen): the speaker column wasn't padded/colon-aligned, and a
      multi-line turn (`"Sergus: Yes.\nI think we left one at least."`) got flattened
      into one wrapped paragraph instead of keeping each original line as its own
      indented output line — matching `examples/example_transcript_001_cleaned.txt`
      turned out not to be the right target after all; the *raw* file's own
      convention (`examples/example_transcript_001.txt`: padded speaker column,
      original line breaks preserved) was. `RegexImporter` now joins a turn's
      continuation lines with `"\n"` instead of `" "` so that structure survives
      into the database (`TranscriptCleaner` already normalizes all whitespace
      including `"\n"` when merging same-speaker lines, so Cleaned output is
      unaffected). `export_plaintext` pads every speaker name to the widest one
      actually present in that transcript (not a hardcoded width — the raw example
      file's own width of 8 is wider than its longest name, 6, for reasons lost to
      whatever produced it), and prints each of a turn's original lines separately,
      only falling back to word-wrap for an individual line/merged-turn long enough
      to need it. Old fixture-diff test replaced with one pinned to a real excerpt of
      `example_transcript_001.txt` (the Windrider/Maldal exchange) plus targeted unit
      tests for padding, wrapping, and blank-line handling.
* Export with timestamps
    * Added 2026-08-13: `export_plaintext(chronicle_id, include_timestamps=False)` -
      when true, prefixes each line with `[HH:MM:SS]` (same `format_timestamp` helper
      the transcript view's timestamp toggle uses) ahead of the padded speaker
      column, using the exact same wrap/hanging-indent rules either way - the
      timestamp prefix is a fixed 11 characters (`"[HH:MM:SS] "`), so it just widens
      the continuation-line indent, nothing about the alignment logic itself changed.
      Export dropdown gained a second item, "Plain text with timestamps (.txt)".
* Wire up the Export button in the transcript view (currently has no handler)
    * Fixed 2026-08-13: replaced with a dropdown (`PopupMenuButton`) — "Plain text" is
      live (`FilePicker.save_file` + write); HTML/PDF/"Chronicle .zip" are listed but
      `disabled=True` ("coming soon") rather than silently absent, so it's honest about
      what's not built yet instead of just missing.

Later:

* PDF — fpdf2 with bundled DejaVu fonts, so every script and every `?` survives
  (ticket 017). See [docs/pdf-export.md](docs/pdf-export.md).
* HTML
* SRT subtitles (Sprint 8), refused for a text import, which has no real timings
* Chronicle export (zip the chronicle's workspace directory to a chosen location)
    * Done 2026-09-15: `TranscriptService.export_zip` packs one chronicle into a `.zip`
      under a single folder named after it — `project.db` plus a `chronicle.json`
      manifest, and `sources/` only when asked for. The database is snapshotted with
      `VACUUM INTO` (`DatabaseManager.snapshot_project`) rather than copied: the project
      engine is cached and may have a connection open, so a file copy could catch a write
      half-made and ship a torn database that looks fine until someone opens it. The
      manifest exists because title, description, kind and tags live in the *workspace*
      database, so a `project.db` lifted out on its own arrives anonymous — and the
      folder name is what `link_external_chronicle` reads the title from, so an unpacked
      archive comes back named correctly either way. Audio is opt-in behind a dialog
      (unticked by default): without it the bundle is a few hundred kilobytes, with it
      it is however many hours of recording. The sources are still listed in the
      manifest, so omitted tracks read as *missing* rather than as never having existed.
      See docs/storage.md.
    * Done 2026-09-15: the Export menu's last `disabled=True` item is gone — every
      format in the dropdown now does something.
* Document exports work in thin-client mode
    * Fixed 2026-09-15: `export_html`, `export_pdf` and `export_zip` are now exposed over
      RPC. They were not reachable remotely at all, and not in a way that failed politely:
      `RemoteServiceProxy` only installs *exposed* methods, so a thin client's Export menu
      raised `AttributeError` on HTML and PDF rather than reporting anything. Exposing
      them needed a transport that can carry documents — a method returning
      `bytes`/`bytearray` is now served as `application/octet-stream` and read back off
      `response.content`, since JSON cannot carry bytes. HTML was only ever unexposed
      because it sat next to the two that could not be. See docs/deployment-and-rpc.md.

### Chronicler Server

* Add server application mode
* Add first run CLI wizard
    * Add option to generate or set API key
* Add API layer
* Add authentication
    * Fixed 2026-08-13: key comparison uses `secrets.compare_digest`; CORS
      `allow_credentials` set to `False` (was `True` alongside a wildcard origin — an
      invalid, unsafe combination, and unnecessary since auth is a header, not a cookie).
* Confine the linked-chronicle paths a remote caller can name (ticket 076)
* Enforce the upload cap before the body is received (ticket 053)
* TLS is left to a reverse proxy or a tunnel. See
  [docs/security.md](docs/security.md#transport).
* Add remote repository implementation
* Connect desktop client to server
    * Fixed 2026-08-13: Thin Client mode (`chronicler/desktop/runtime.py`). Verified
      live against a real running server, not just `ASGITransport` — which is what
      surfaced the three RPC-layer bugs listed under Sprint 3 above.
* Fix server startup (Sprint 1)
* Harden `/upload` — filename sanitisation, size limit, collision handling
    * Fixed 2026-08-13: server-generated `uuid4()` filenames (whitelisted extension
      only), 500MB size cap with partial-file cleanup on overflow, collisions are
      statistically impossible by construction.
* Move `python-multipart` into base dependencies (`/upload` 500s without it)

### Testing

* Repository tests (chronicle, task, tag)
* Container tests
* RPC round-trip tests (server + remote proxy)
* Importer and cleaner tests
* Consolidate the duplicated flat and mirrored test layouts under `tests/chronicler/`
    * Done 2026-08-13. This was also a live break, not just duplication: two files
      named `test_importers.py` with no `__init__.py` anywhere under `tests/` made
      pytest's rootless collection abort with `import file mismatch` — a plain `pytest`
      invocation couldn't run the suite at all.
* Investigate six deleted tests whose stale `.pyc` remain on disk — `test_server_routes`,
  `test_config_validation`, `test_wizard_api_key`, `test_wizard_partial`, `repro_issue`,
  `repro_404`.
    * Investigated 2026-08-13: none are in git history (`git log --all --diff-filter=D`
      and full reflog both checked) — they were written and deleted locally without ever
      being committed, so there's nothing to restore. `test_server_routes`,
      `test_config_validation` and `test_wizard_api_key`/`test_wizard_partial` were
      reconstructed as real coverage from their names' evident intent.
      `repro_issue`/`repro_404` were not — no surviving signal (docstring, linked issue,
      commit) of what they targeted, so reconstructing them would just be guessing.
* Server startup smoke test
* Web client auth / proxy tests
* Worker claiming and retry tests (added 2026-08-13)
* Migration tests (added 2026-08-13 — `alembic_version` stamped at head, idempotent
  re-init/re-open)
* `SQLiteTagRepository` tests (was zero coverage, fixed 2026-08-13)
* Thin Client end-to-end tests (added 2026-08-13) — `RemoteContainer` round-trips
  through a real `RpcServer`, plus one actual live smoke test against a real running
  `chronicler server` process (not `ASGITransport`), which is what caught the three RPC
  bugs under Sprint 3 that every `ASGITransport`-based test had missed. Worth
  remembering as a general lesson: in-process ASGI transport tests don't exercise real
  JSON (de)serialization the same way a genuine HTTP round-trip does.
* Mirror the test tree to the package tree (2026-08-17). `tests/chronicler/` now
  matches `chronicler/` module for module, as real packages — the mirrored layout repeats
  module names (`views/archive/test_view.py` and `views/transcript/test_view.py`), which
  pytest's default import mode can only disambiguate for packages.
* De-duplicate test fixtures (2026-08-17). The `async_session` fixture was copy-pasted
  identically into four modules; it lives in `tests/conftest.py` now. `attach_page`
  (`tests/chronicler/desktop/conftest.py`) replaces the try/finally `patch.object(...,
  "page")` block every desktop test hand-rolled, and fixture-file paths come from
  `tests/paths.py` instead of `Path(__file__).parents[n]` — which silently pointed at the
  wrong directory the moment a test module moved.
* Tests run on Windows in CI, and hold up there (tickets 003, 005)
* A fixture for a second connection holding the write lock (ticket 002)
* Optional extras in CI (ticket 044)
