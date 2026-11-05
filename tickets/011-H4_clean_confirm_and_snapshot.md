# 011-H4_clean_confirm_and_snapshot

## Clean rewrites the transcript with no confirmation or undo

### info

| | |
| --- | --- |
| importance | high |
| danger level | High: one click permanently changes data that cannot be regenerated. Change risk: low. |
| reach | All modes, from the archive card and the chronicle view |
| effort | S |
| evidence | read in code; line counts measured |
| touches | `chronicler/desktop/operations.py`, `chronicler/core/processing/handlers/cleaning.py`, `chronicler/core/database_manager.py`, i18n catalogues |

### description

`ChronicleOperations.clean` (`operations.py:74-77`) queues the task immediately, and the
handler deletes every line and writes the cleaned set (`cleaning.py:51-52`). On the
example transcript, 1,686 turns became 1,242. Defaults drop lines such as "You." and merge
consecutive turns, which also loses per-segment timing.

Deleting a single line asks for confirmation, and `TODO.md` itself says transcript text
"cannot be regenerated".

### proposed fix

1. Ask for confirmation in `ChronicleOperations.clean`, which both the archive card and
   the chronicle view use.
2. In `handle_clean`, before opening the transaction, call the existing `snapshot_project`
   to write `snapshots/before-clean-<timestamp>.db` beside the chronicle's `project.db`.
   `VACUUM INTO` cannot run inside a transaction, and it refuses to overwrite, so names
   must be unique. Keep the last 3.
3. Linked chronicles keep snapshots beside their external `project.db`.

The restore UI is its own ticket.

Done when Clean asks first, and a snapshot containing the original lines exists
afterwards.

### related tickets

- (BLOCKS) [032-S4_project_db_access](032-S4_project_db_access.md): edits the clean handler
- (BLOCKS) [040-S6_worker_and_handlers](040-S6_worker_and_handlers.md): edits the clean handler
- (BLOCKS) [065-F3_restore_snapshots](065-F3_restore_snapshots.md): provides the snapshots
