# 083-L18_speaker_case_duplicates

## Typing a speaker in different case creates a second speaker in the chronicle

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: a near-duplicate speaker that exports and summaries treat as a different person. Change risk: low. |
| reach | Editor, transcribe dialog, import and clean, in all modes |
| effort | S |
| evidence | read in code |
| touches | `chronicler/core/sqlite/transcript_repository.py`, `chronicler/core/services/transcript_service.py`, `tests/` for both, `docs/speakers.md` |

### description

The workspace registry matches names after normalising them (`normalize_speaker_name`:
whitespace collapsed, case folded), so `GM`, `gm` and ` GM ` count as one known speaker.
Inside a chronicle, `SQLiteTranscriptRepository.get_or_create_speaker` matches the exact
string. Typing `gm` on a line in a chronicle that has `GM` therefore creates a second
`speakers` row. The registry still lists one name, but `speaker_suggestions` merges the
chronicle's own names case-sensitively, so the next speaker picker offers both `GM` and
`gm`.

This matters more now that the editor is where new speakers get added on the fly: an NPC
the GM voices is typed in by hand, often more than once and in different case.

All four callers go through `get_or_create_speaker`: `TranscriptService.update_line`,
`TranscriptService.assign_speaker`, `handlers/base.py` (import and clean) and
`handlers/transcribing.py`.

### proposed fix

Make `get_or_create_speaker` match on the normalised name, with the same rule as the
registry, and keep the first spelling it saw, as the registry does. Strip and collapse
whitespace before creating a new speaker. Make `speaker_suggestions` deduplicate on the
normalised name, preferring the registry's spelling.

No migration: existing duplicate rows stay as they are, and new writes stop creating
them. If more than one existing row matches, take the oldest.

### related tickets

- (BLOCKER) [040-S6_worker_and_handlers](040-S6_worker_and_handlers.md): reshapes the handlers that call this
- (RELATED) [043-S16_split_transcript_service](043-S16_split_transcript_service.md): moves the service methods this touches. If it is still open, take it first or drop it
- (BLOCKS) [084-F6_new_speaker_in_editor](084-F6_new_speaker_in_editor.md)
- (RELATED) [051-L7_speaker_count_definition](051-L7_speaker_count_definition.md): duplicates also inflate the speaker count
