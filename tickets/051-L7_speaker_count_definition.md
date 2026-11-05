# 051-L7_speaker_count_definition

## Speaker count has two definitions

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: a wrong number in the UI. Change risk: low. |
| reach | All modes |
| effort | XS |
| evidence | read in code |
| touches | `chronicler/core/services/transcript_service.py`, `chronicler/core/processing/handlers/` |

### description

`handle_transcribe` counts distinct names on lines (`transcribing.py:121`), while
`refresh_speaker_count` counts rows in the speakers table
(`transcript_service.py:329-330`). Speaker rows outlive their lines on purpose. Editing or
deleting lines updates neither.

### proposed fix

Use one definition in `reconcile`: speakers with at least one line. Call it after
`update_line` and `delete_line`.

Done when deleting a speaker's last line lowers the count.

### related tickets

- (BLOCKER) [040-S6_worker_and_handlers](040-S6_worker_and_handlers.md): builds on `reconcile`
