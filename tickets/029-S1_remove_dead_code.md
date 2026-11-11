# 029-S1_remove_dead_code

## Remove dead code and unused columns

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Low: maintenance cost only. Change risk: low. |
| reach | Internal. About 150 lines |
| effort | S |
| evidence | scanned with vulture, each confirmed by search |
| touches | `chronicler/core/repositories.py`, `chronicler/core/sqlite/`, `chronicler/core/local_container.py`, `chronicler/core/database_manager.py`, `chronicler/core/rpc.py`, `chronicler/core/remote.py`, `chronicler/core/processing/summarizer.py`, `chronicler/desktop/app.py`, `chronicler/desktop/dialogs.py`, `chronicler/desktop/views/transcript/actions.py`, `chronicler/desktop/views/settings/view.py`, new migrations in both chains |

### description

No production caller:

- `run_app` (`desktop/app.py:354`), `ask_text` (`desktop/dialogs.py:78`)
- `DatabaseManager.get_chronicle_sources_path`
- `ChronicleActions.transcript_import_confirmed`, `edit_save_clicked`
- `TagRepository` and `SQLiteTagRepository`: registered, never resolved
- `TranscriptRepository.add_line` (`search` is used since 063)
- `KnownSpeakerRepository.search`, `AudioSourceRepository.delete`,
  `SQLiteSummaryRepository.get`
- `SummaryDraft.chunk_summaries`, `RemoteServiceProxy._cls`
- `get_services` and the fallback in `RpcServer.build`, which only tests reach
- `amber_button` re-exported through `settings/view.py:495`

Columns no feature uses: `chronicles.source_file`, `known_speakers.uses`, `first_seen`,
`last_used`, `audio_sources.duration_seconds`.

Leave these for other tickets: `Settings.is_workspace_valid` (gets wired in),
`SystemService.ping` (the smoke test will use it), `tags.color` (tag management decides).

### proposed fix

Delete the code and the tests that only exercise it. Drop the columns in one migration per
chain, and remove the `source_file` argument from `create_chronicle`.

Done when vulture no longer reports these, and the suite passes.

### related tickets

- (BLOCKS) [030-S2_remove_repository_abcs](030-S2_remove_repository_abcs.md): removes the unused methods first
- (BLOCKS) [066-F4_tag_management](066-F4_tag_management.md): removes `TagRepository`, which this should not revive
- (RELATED) [055-L11_workspace_validation](055-L11_workspace_validation.md): keep `is_workspace_valid`, which that ticket wires in
- (RELATED) [066-F4_tag_management](066-F4_tag_management.md): keep `tags.color` for that ticket to decide on
- (RELATED) [075-L13_edit_drops_computed_duration](075-L13_edit_drops_computed_duration.md): changes how the same model is updated
