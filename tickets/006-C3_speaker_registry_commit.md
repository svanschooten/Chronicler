# 006-C3_speaker_registry_commit

## Saving a speaker locks the workspace database, then loses the write

### info

| | |
| --- | --- |
| importance | critical |
| danger level | High: triggers the worker failure below, and speaker names vanish. Change risk: very low. |
| reach | Full stack and thin client, on "Save speaker only" and on changing a speaker in the transcript editor |
| effort | XS |
| evidence | reproduced |
| touches | `chronicler/core/sqlite/known_speaker_repository.py`, `tests/chronicler/core/services/test_audio_sources.py`, `test_transcript_editing.py`, `test_linking.py` |

### description

`TranscriptService._remember_speaker` (`transcript_service.py:295-302`) calls
`register()`, which flushes (`known_speaker_repository.py:44`). Nothing commits. Until
something else commits on that session, the open view holds the write lock on
`chronicler.db`.

Pressing Transcribe queues a task straight afterwards, and that commit also saves the
speaker, so the normal path looks fine. "Save speaker only" and editing a line's speaker
do not get that accidental commit.

```text
second connection sees the new speaker    no
second writer while the view is open      database is locked, after 5.47 s
after the view closes                     row is gone
through the HTTP API                      known_speakers has 0 rows
```

The tests miss it because they read back through the same session, which sees its own
uncommitted flush (`test_audio_sources.py:176`, `test_transcript_editing.py:113`,
`test_linking.py:185`).

### proposed fix

Commit in `SQLiteKnownSpeakerRepository.register`, as the chronicle and task repositories
already do. Roll back on failure inside it too, because `_remember_speaker` swallows
exceptions and would otherwise leave the session unusable.

Change the tests above to read through a second session, using the new fixture.

Done when another connection sees the speaker immediately, and a second writer succeeds
while the view stays open.

### related tickets

- (BLOCKER) [002-T2_two_connection_test_fixture](002-T2_two_connection_test_fixture.md): uses the two-connection fixture
- (RELATED) [007-C2_worker_session_per_step](007-C2_worker_session_per_step.md): this bug is the easiest way to trigger that one, but they can be fixed in either order
