# Chronicler tickets

Work items from the [code audit](https://claude.ai/artifact/4UyF8zjA2naKYccfSTb7V7) of
commit `b02421a`. Line numbers in tickets 001-066 refer to that commit. The report is a
private page until its owner shares it, and every ticket stands on its own without it.

Tickets 067-071 came out of reviewing the first merged work. Tickets 072-081 came out of a
review of the whole application after wave 4, which also re-checked every open ticket
against the code, re-baselined `TODO.md`, and set the order of the open waves below.

## How to use this list

- **The waves are the recommended order.** Waves 1-4 are done. Within an open wave,
  tickets are listed in the order to take them, which is not always numeric.
- Numbers 001-066 were assigned by importance, then dependencies. Later tickets got the
  next free number, so their numbers say nothing about their order: each sits in the wave
  where it belongs.
- A blocker always sits in an earlier wave, or earlier in the same wave, than the ticket
  it blocks.
- Pick any ticket whose blockers are merged. Most tickets inside a wave can run in
  parallel; the coordination table below says which cannot.
- One ticket, one branch, one PR. Update the docs your change affects in the same PR.
- A ticket marked *closed by* needs no work of its own. It stays here to record the
  problem, and gets ticked along with the ticket that closes it.

## Claiming a ticket

Change its `[ ]` to `[x]` in the list below. Commit only that change and get it onto
your feature branch and into a draft PR before you start, so everyone else can see it. `git blame` on this file shows who
claimed what, and closing the PR and deleting the stale branch gives a ticket back.

Keep the blank line between tickets. Without it, two people claiming neighbouring tickets
get a merge conflict.

## Coordinating parallel work

These areas conflict when worked on at the same time, so take their tickets in this order.
Merged tickets are left in for context.

| Area | Order | Why |
| ---- | ----- | --- |
| Worker and task queue | 007 → 009 → 069 → 022 → 077 → 064 → 040 | Same files in `core/workers.py` and `task_repository.py` |
| Task handlers | 010 → 011 → 035 → 032 → 064 → 040 | Same files in `core/processing/handlers/` |
| Project migrations | 010 → 020 → 074 → 063 → 029 | Each adds an Alembic revision on the project chain (head `c5e8a1f3d920`). Rebase `down_revision` on whatever merged last. 074 settles the compatibility rule before the next revision |
| Archive migrations | 022 → 029 | Same for the archive chain (head `b4d7e2a9c156`) |
| Chronicle service and repository | 072 → 032 → 076 → 075 → 029 → 066 | Same parts of `chronicle_service.py` and `chronicle_repository.py` |
| Archive view | 072 → 063 → 078 | Same parts of `desktop/views/archive/view.py` |
| Dialogs and recording | 073 → 036 | Same code in `desktop/dialogs.py` and `views/transcript/recording.py` |
| Desktop shell | 007 → 027 → 041 | Same parts of `desktop/app.py`. Schedule 041 alone, because it conflicts with most open desktop work |
| Runtime locks | 016, 067, then 035 | Each regenerates `scripts/runtime/locks/`. Merge one, then regenerate on top of it |
| CI workflow | 004 → 005 → 044 | Same file |
| Release workflow | 081 → 059 | Same file |

## Reading a ticket

A ticket has a `proposed fix` section only where there is a real proposal. Without one,
the description says what is wrong and the approach is yours to choose.

Each ticket has an info table:

| Field | Meaning |
| ----- | ------- |
| importance | `critical`, `high`, `medium` or `low`: how urgent it is |
| danger level | What goes wrong if it is left alone, followed by the risk of making the change |
| reach | Who or what it affects |
| effort | `XS` under an hour, `S` up to half a day, `M` one or two days, `L` several days. These are estimates |
| evidence | `reproduced` means run against the real code. `read in code` means traced but not run. `inferred` means it follows from other evidence |
| touches | Files it changes, so you can spot a conflict before starting |

Related tickets use these labels:

| Label | Meaning |
| ----- | ------- |
| `(BLOCKER)` | Must be merged before this ticket starts |
| `(BLOCKS)` | Waits on this ticket |
| `(CLOSED BY)` | That ticket also resolves this one |
| `(CLOSES)` | This ticket also resolves that one |
| `(RELATED)` | Same area, with no required order |

The ID in each name comes from the audit report: `C` critical, `H` high, `M` medium, `L`
lower priority, `S` simplification, `P` performance, `T` tests and CI, `D` documentation,
`F` feature, and `A` an architecture decision. Later tickets continue each series.

## Tickets

### Wave 1: baseline, so parallel work is safe

- [x] [001-C1 A fresh install cannot start](001-C1_sqlalchemy_asyncio_extra.md) · critical · XS

- [x] [002-T2 Tests cannot simulate a locked database](002-T2_two_connection_test_fixture.md) · high · XS · after 001

- [x] [003-T1 11 tests fail on Windows, and test isolation does not hold there](003-T1_windows_test_portability.md) · high · S · after 001

- [x] [004-S12 CI and install files carry a lot of avoidable text](004-S12_ci_and_install_cleanup.md) · medium · S · after 001

- [x] [005-T3 CI never runs on Windows, a platform you ship to](005-T3_windows_in_ci.md) · high · XS · after 003, 004

### Wave 2: stop losing work

- [x] [006-C3 Saving a speaker locks the workspace database, then loses the write](006-C3_speaker_registry_commit.md) · critical · XS · after 002

- [x] [007-C2 One lock timeout stops all background work until restart](007-C2_worker_session_per_step.md) · critical · S · after 002

- [x] [008-A1 Nothing stops two processes from sharing a workspace](008-A1_single_process_workspace_lock.md) · high · S

- [x] [009-C4 Interrupted tasks stay WORKING forever](009-C4_task_recovery.md) · critical · S · after 007, 008

- [x] [010-C5 Transcribing a second track for a speaker deletes the first](010-C5_transcript_line_source_id.md) · critical · M

- [x] [011-H4 Clean rewrites the transcript with no confirmation or undo](011-H4_clean_confirm_and_snapshot.md) · high · S

### Wave 3: close the security exposure

- [x] [012-S14 Remove the web client](012-S14_remove_web_client.md) · high · S

- [x] [013-H2 The web client exposes the full API with no login](013-H2_web_client_open_proxy.md) · high · closed by 012

- [x] [014-M8 Audio uploads from the web client always fail](014-M8_web_audio_upload_fails.md) · medium · closed by 012

- [x] [015-H3 The API key is logged, and secrets from the environment get saved to disk](015-H3_protect_api_keys.md) · high · S

- [x] [016-H1 Released binaries ship without server mode](016-H1_server_component_for_binaries.md) · high · S · after 001, 012

### Wave 4: wrong output and robustness

- [x] [017-M1 PDF export removes every question mark and all non-Latin-1 text](017-M1_pdf_text_loss.md) · medium · S

- [x] [018-M2 The default importer folds non-ASCII speakers into the previous turn](018-M2_unicode_speaker_names.md) · medium · XS

- [x] [019-M5 Every thin-client call has a 5-second timeout](019-M5_rpc_timeouts.md) · medium · XS

- [x] [020-M3 The subtitle guard stops working after a clean or a line delete](020-M3_explicit_timing_flag.md) · medium · S · after 010

- [x] [021-M10 Reading an unknown chronicle creates it on disk](021-M10_reads_must_not_create_chronicles.md) · medium · S

- [x] [022-M6 Retries run about one second apart](022-M6_retry_backoff.md) · medium · S · after 009

- [x] [023-S7 Replace the model registry cache with one call](023-S7_model_list_single_call.md) · medium · S

- [x] [024-M4 Thin clients never see model errors](024-M4_thin_client_model_errors.md) · medium · closed by 023

- [x] [025-S9 Replace the three mode vocabularies with one enum](025-S9_single_mode_enum.md) · medium · S · after 012

- [x] [026-M9 A web-client config crashes the desktop app](026-M9_stale_mode_crashes_desktop.md) · medium · closed by 012

- [x] [027-M7 A finished task rebuilds the view on screen](027-M7_refresh_view_in_place.md) · medium · M

- [x] [028-P1 PDF and zip exports freeze the app](028-P1_exports_off_event_loop.md) · medium · XS

- [x] [067-M11 The normalization extra does not install numpy, which normalizing needs](067-M11_normalization_extra_numpy.md) · medium · XS

- [x] [068-M12 Any failure to lock a workspace reads as "already open in another process"](068-M12_workspace_lock_error_reasons.md) · medium · XS

### Wave 5: quick fixes people would notice

Small and independent. Users hit the first four, and the rest are under an hour each.

- [x] [072-M13 A failed link leaves a broken chronicle, and Link cannot work on a thin client](072-M13_failed_link_leaves_chronicle.md) · medium · S

- [x] [049-L5 "Open folder" on a thin client tries to open a server path](049-L5_open_folder_thin_client.md) · low · XS · after 025

- [x] [073-M14 Dismissing a dialog leaves its action waiting forever, and a recording keeps running](073-M14_dismissed_dialogs_hang.md) · medium · S

- [x] [069-L12 A finished task's event is lost when the database is busy](069-L12_completion_event_on_busy_database.md) · low · XS · after 009

- [x] [054-L10 Config files can be misread and overwritten](054-L10_config_encoding_and_atomic_save.md) · low · XS · after 015

- [x] [055-L11 Workspace validation exists but never runs](055-L11_workspace_validation.md) · low · XS

- [x] [039-P4 Checking extras can stall startup](039-P4_extras_check_off_event_loop.md) · low · XS

- [x] [038-P3 Slow imports that most runs never use](038-P3_lazy_imports.md) · low · XS

- [x] [061-D3 Version and project status disagree](061-D3_version_and_status.md) · low · XS

- [x] [070-T7 Dependabot misses the shared setup action and opens floor-only PRs](070-T7_dependabot_config.md) · low · XS

### Wave 6: safety, then search

Stop a pattern from freezing the app, make opening chronicles cheap, settle what a shared chronicle's schema promises, then build the search the tagline promises. CI starts covering the optional extras alongside, and the server's two remaining hardening items close.

- [x] [035-S11 Replace the regex guard with a real timeout, so a pattern cannot freeze the app](035-S11_regex_timeout_instead_of_guard.md) · medium · S

- [x] [031-S5 Project databases keep a thread and a file open per chronicle](031-S5_nullpool_project_engines.md) · medium · XS

- [x] [032-S4 Give project database access one helper and one owner](032-S4_project_db_access.md) · medium · M · after 010, 011, 021

- [x] [033-L1 Three panel loads share one database session](033-L1_shared_session_panel_loads.md) · low · closed by 032

- [x] [074-A2 A chronicle opened by a newer Chronicler cannot be opened by an older one](074-A2_schema_versions_for_shared_chronicles.md) · medium · S

- [x] [063-F1 Full-text transcript search](063-F1_full_text_search.md) · medium · L · after 031, 032, 020, 074

- [x] [044-T4 Optional extras never run in CI](044-T4_extras_ci_job.md) · medium · S · after 004

- [x] [057-P6 Normalization decodes the file three times](057-P6_normalization_single_pass.md) · low · S · after 044

- [x] [076-L14 Remote callers can point a chronicle at any path on the server](076-L14_project_path_from_rpc_callers.md) · low · S

- [x] [053-L9 The upload cap does not limit what is received](053-L9_upload_size_cap.md) · low · S

### Wave 7: what users notice next

Progress and cancel for long transcriptions, explanations that reach thin clients, finished translations, unattended server setup and undo.

- [x] [077-L15 The task list keeps every task ever run](077-L15_task_history_grows.md) · low · S

- [x] [064-F2 Real transcription progress and cancel](064-F2_progress_and_cancel.md) · medium · M · after 009, 022

- [x] [046-L2 Service errors reach thin clients as a bare 500](046-L2_rpc_error_mapping.md) · low · S

- [x] [047-L3 17 interface strings bypass translation](047-L3_finish_translation.md) · low · S

- [x] [042-S10 Replace the console wizard with flags](042-S10_console_wizard_to_flags.md) · medium · S · after 012, 025

- [x] [065-F3 Restore after destructive actions](065-F3_restore_snapshots.md) · medium · M · after 011, 031

- [x] [075-L13 Saving the edit dialog can erase a duration a task just computed](075-L13_edit_drops_computed_duration.md) · low · S

- [x] [078-L16 Archive search can show results for an earlier query](078-L16_archive_search_out_of_order.md) · low · XS

- [x] [079-L17 Some model replies crash the summary or end up in it](079-L17_llm_reply_shapes.md) · low · XS

- [x] [048-L4 Any file in sources/ counts as an audio track](048-L4_audio_file_filter.md) · low · XS

- [x] [050-L6 The summary recap is not budgeted](050-L6_recap_budget.md) · low · S

- [x] [052-L8 Local models reload too often or are never released](052-L8_model_lifetimes.md) · low · S

- [x] [037-P2 Zip exports hold everything in memory](037-P2_streamed_zip_export.md) · medium · M · after 028

- [ ] [056-P5 The transcript editor builds every row up front](056-P5_editor_windowing.md) · low · M

### Wave 8: docs

`TODO.md` was re-baselined in the review after wave 4, so the split is mechanical now.

- [ ] [060-D2 Top-level docs have drifted from the code](060-D2_fix_doc_drift.md) · medium · S

- [ ] [062-D1 TODO.md is a changelog, a roadmap and a design archive at once](062-D1_split_todo.md) · low · S · after 012

### Wave 9: CI and test hygiene

Safe to take in parallel with anything above, at any time.

- [ ] [045-T5 Tighten Ruff's rules and target version](045-T5_ruff_rules_and_target.md) · low · S

- [ ] [080-T9 The test suite is not warning-free under coverage](080-T9_warning_free_tests.md) · low · XS

- [ ] [081-T10 Release builds do not run the tests](081-T10_release_runs_tests.md) · low · XS

- [ ] [071-T8 Two tests pass for a reason other than the one they state](071-T8_tests_that_pass_for_the_wrong_reason.md) · low · XS

- [ ] [058-T6 Nothing verifies the real rendered UI](058-T6_ui_rendering_checks.md) · low · M

### Wave 10: simplify the foundations, one at a time

Internal only, and the most likely to conflict, so these come after the user-facing work. Schedule 041 alone. 043 has the least value of anything here: take it last, or drop it.

- [ ] [029-S1 Remove dead code and unused columns](029-S1_remove_dead_code.md) · medium · S

- [ ] [030-S2 Remove the repository interfaces](030-S2_remove_repository_abcs.md) · medium · S · after 029

- [ ] [034-S8 Reduce the handshake to one function](034-S8_simplify_handshake.md) · low · XS

- [ ] [036-S13 Share the desktop's repeated helpers](036-S13_desktop_helpers.md) · low · XS

- [ ] [040-S6 Simplify the worker and its handlers](040-S6_worker_and_handlers.md) · medium · M · after 007, 009, 022, 010, 011, 032

- [ ] [051-L7 Speaker count has two definitions](051-L7_speaker_count_definition.md) · low · XS · after 040

- [ ] [041-S3 Replace the DI container with an explicit Services object](041-S3_services_bundle.md) · medium · M · after 030, 023, 034, 025, 019, 027

- [ ] [066-F4 Tag management](066-F4_tag_management.md) · low · M · after 029

- [ ] [043-S16 Split TranscriptService](043-S16_split_transcript_service.md) · low · M · after 041, 032, 037

### Wave 11: waiting on a decision

Start only once one release of the runtime build has been used.

- [ ] [059-S15 Retire the PyInstaller build](059-S15_retire_pyinstaller.md) · medium · S · after 016
