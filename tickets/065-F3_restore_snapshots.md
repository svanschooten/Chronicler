# 065-F3_restore_snapshots

## Restore after destructive actions

### info

| | |
| --- | --- |
| importance | medium |
| danger level | None: a missing feature that completes the data-safety work. Change risk: medium, replaces live database files. |
| reach | All modes |
| effort | M |
| evidence | read in code |
| touches | `chronicler/core/database_manager.py`, `chronicler/core/services/`, `chronicler/core/processing/handlers/importing.py`, `transcribing.py`, `chronicler/desktop/views/transcript/actions.py`, i18n catalogues |

### description

The clean ticket writes snapshots, and nothing can use them yet. Overwriting an import and
re-transcribing are destructive too.

### proposed fix

1. Add a "Restore previous version" action listing a chronicle's snapshots.
2. Restore by closing the project, then swapping the file with `os.replace` after
   snapshotting the current state. Nothing may reopen the database between closing it
   and the swap: the transcript view loads three panels at once, and any of them would
   reopen it. Hold a per-chronicle lock that `_project_engine` also takes.
3. Also snapshot before an overwriting import and before re-transcribing.

Done when a clean, an overwrite and a re-transcribe can each be undone.

### related tickets

- (BLOCKER) [011-H4_clean_confirm_and_snapshot](011-H4_clean_confirm_and_snapshot.md): provides the snapshots
- (BLOCKER) [031-S5_nullpool_project_engines](031-S5_nullpool_project_engines.md): with pooled connections, a held file handle makes the swap fail on Windows
- (RELATED) [010-C5_transcript_line_source_id](010-C5_transcript_line_source_id.md): re-transcribing replaces hand edits
