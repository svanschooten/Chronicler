# 032-S4_project_db_access

## Give project database access one helper and one owner

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Low: repetition. It also removes a latent concurrency error. Change risk: medium, touches every handler. |
| reach | Internal. About 80 lines |
| effort | M |
| evidence | read in code; concurrency error reproduced |
| touches | `chronicler/core/database_manager.py`, `chronicler/core/services/transcript_service.py`, `chronicler/core/services/chronicle_service.py`, `chronicler/core/processing/handlers/` |

### description

- 7 blocks repeat `try / commit / except: rollback`, although `async with session` already
  rolls back on exit.
- A chronicle's location is resolved in 4 places: `TranscriptService._project_path`,
  `HandlerBase.project_path_for`, inline in `add_audio_source`, and in
  `chronicle_directory`. It is built by hand in 4 places.
- `custom_path` is threaded through 3 `DatabaseManager` methods.
- Each lookup costs 2 queries on the caller's shared session.

### proposed fix

Add a helper, and let `DatabaseManager` resolve and cache each chronicle's location
through its own short session, invalidating when `project_path` changes:

```python
@asynccontextmanager
async def transaction(self, chronicle_id: UUID):
    session = await self.project_session(chronicle_id)
    async with session, session.begin():
        yield session
```

This sketch has not been run.

Done when no `custom_path` argument remains outside `DatabaseManager`, the rollback blocks
are gone, and three concurrent panel loads on an empty connection pool all succeed (add
that as a regression test).

### related tickets

- (BLOCKER) [010-C5_transcript_line_source_id](010-C5_transcript_line_source_id.md): edits the transcribe handler
- (BLOCKER) [011-H4_clean_confirm_and_snapshot](011-H4_clean_confirm_and_snapshot.md): edits the clean handler
- (BLOCKER) [021-M10_reads_must_not_create_chronicles](021-M10_reads_must_not_create_chronicles.md): changes how databases get created
- (BLOCKS) [040-S6_worker_and_handlers](040-S6_worker_and_handlers.md): handlers should use the new helper first
- (BLOCKS) [043-S16_split_transcript_service](043-S16_split_transcript_service.md): uses the project database helper
- (BLOCKS) [063-F1_full_text_search](063-F1_full_text_search.md): uses the project database helper
- (CLOSES) [033-L1_shared_session_panel_loads](033-L1_shared_session_panel_loads.md): location lookups get their own session
- (RELATED) [031-S5_nullpool_project_engines](031-S5_nullpool_project_engines.md): same class
