# 010-C5_transcript_line_source_id

## Transcribing a second track for a speaker deletes the first

### info

| | |
| --- | --- |
| importance | critical |
| danger level | High: loses transcript lines and reports success. Change risk: medium, adds a migration. |
| reach | Any chronicle with two tracks for one speaker: split recordings, rejoined Discord users, repeat in-app recordings |
| effort | M |
| evidence | reproduced |
| touches | `chronicler/core/project_database.py`, `chronicler/core/models.py`, new migration in `chronicler/migrations/project/`, `chronicler/core/sqlite/transcript_repository.py`, `chronicler/core/repositories.py`, `chronicler/core/processing/handlers/transcribing.py`, `chronicler/core/processing/cleaners.py`, `chronicler/desktop/views/transcript/transcribe_dialog.py`, i18n catalogues |

### description

`handle_transcribe` clears old output with `delete_lines_by_speaker`
(`transcribing.py:100-101`). Transcript lines have no link to the track that produced them
(`project_database.py:19-28`), so this removes everything that speaker has said. Both
tracks then report as transcribed. Re-transcribing also discards any hand edits on that
speaker's lines.

```text
after part1.wav as Alice     3 lines
after part2.wav as Alice     3 lines, all from part2
sources reporting done       part1.wav, part2.wav
```

### proposed fix

1. Add a nullable `source_id` to `transcript_lines`, pointing at `audio_sources.id`, and
   to `TranscriptLine`.
2. Set it in `handle_transcribe`, and delete by source instead of by speaker.
3. Older rows have no source. If the speaker has exactly one transcribed source, treat
   their `NULL` lines as belonging to it. Otherwise keep them.
4. In `MergeSameSpeaker` (`cleaners.py:148-166`), merge only lines from the same source,
   so a merged line never spans two tracks.
5. Add an optional start offset per source, defaulting to 0. Timestamps are used as-is,
   which is right for time-aligned tracks but makes sequential parts interleave.
6. Warn in the transcribe dialog before re-running a transcribed track, since hand edits
   on its lines are replaced.

Done when transcribing `part1.wav` and `part2.wav` for one speaker keeps both, re-running
`part2.wav` replaces only its lines, and an existing `project.db` migrates cleanly.

### related tickets

- (BLOCKS) [020-M3_explicit_timing_flag](020-M3_explicit_timing_flag.md): both add a project migration on the same table, so this one rebases on it
- (BLOCKS) [032-S4_project_db_access](032-S4_project_db_access.md): edits the transcribe handler
- (BLOCKS) [040-S6_worker_and_handlers](040-S6_worker_and_handlers.md): edits the transcribe handler
- (RELATED) [020-M3_explicit_timing_flag](020-M3_explicit_timing_flag.md): both add a project migration on the same table, so this one goes first
- (RELATED) [065-F3_restore_snapshots](065-F3_restore_snapshots.md): re-transcribing replaces hand edits
