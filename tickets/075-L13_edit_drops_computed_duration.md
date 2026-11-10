# 075-L13_edit_drops_computed_duration

## Saving the edit dialog can erase a duration a task just computed

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: the duration is lost until the next transcription recomputes it. Change risk: low. |
| reach | All modes, mostly thin clients, whose archive is not refreshed when a task finishes |
| effort | S |
| evidence | reproduced |
| touches | `chronicler/core/services/chronicle_service.py`, `chronicler/core/sqlite/chronicle_repository.py`, `chronicler/desktop/forms.py`, `chronicler/desktop/operations.py`, `tests/chronicler/core/services/test_chronicle_service.py`, `tests/chronicler/desktop/test_operations.py` |

### description

Found in the review after wave 4.

`begin_edit` fills the edit form from the chronicle the card was drawn with
(`operations.py:167-170`). `finish_edit` re-reads the chronicle before saving
(`operations.py:189`), so status and speaker count stay current, but
`EditChronicleForm.apply_to` (`forms.py:91-101`) writes the form's duration field over
the fresh value.

Reproduced: open *Edit* on a new chronicle, let a transcription set its duration to
`1h 24m`, rename it and save. The duration is `None` afterwards.

Duration is both computed by the transcribe handler and editable by hand, so the form
cannot tell "the user cleared it" from "the form never saw it".

More generally, `update_chronicle` is exposed over RPC and takes a whole `Chronicle`, and
`SQLiteChronicleRepository.update` (`chronicle_repository.py:50-68`) writes every field
from it, including `status`, `speakers_count` and `project_path`. Any caller with an old
copy overwrites newer values.

### proposed fix

1. Give the service an edit method that takes only what a user may edit (title,
   description, kind, duration), and write only the fields that changed from what the
   form was filled with.
2. Keep the whole-object `update` internal to the service layer, and stop exposing it
   over RPC.

Done when the reproduction above keeps the computed duration, and a remote caller cannot
set `status`, `speakers_count` or `project_path` directly.

### related tickets

- (RELATED) [076-L14_project_path_from_rpc_callers](076-L14_project_path_from_rpc_callers.md): `update_chronicle` is one of the routes that accepts a `project_path`
- (RELATED) [029-S1_remove_dead_code](029-S1_remove_dead_code.md): removes `source_file` from the same model
