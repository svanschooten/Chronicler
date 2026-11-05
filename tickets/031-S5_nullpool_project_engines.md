# 031-S5_nullpool_project_engines

## Project databases keep a thread and a file open per chronicle

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Medium: slow resource growth on a long-running server. Change risk: low. |
| reach | Full stack and server |
| effort | XS |
| evidence | measured |
| touches | `chronicler/core/database_manager.py`, `docs/storage.md`, `TODO.md` |

### description

Each chronicle opened keeps a pooled connection, which holds a thread and an open file.
Threads went from 2 to 52 after opening 50 chronicles. This caused the Windows delete
failure, `close_project` and the retry logic around it, and the open LRU item in
`TODO.md`.

### proposed fix

Pass `poolclass=NullPool` at `database_manager.py:113`. Measured cost per unit of work:
0.90 ms pooled, 2.10 ms with `NullPool`.

Keep the engine cache, which also records that a database has been migrated. Simplify
`close_project` and update `docs/storage.md:81-99`. Keep `remove_directory`'s retries,
because they also cover virus scanners.

Done when opening 50 chronicles leaves the thread count flat, and deleting a chronicle
works on Windows.

### related tickets

- (BLOCKS) [063-F1_full_text_search](063-F1_full_text_search.md): needs cheap opens for the fan-out
- (RELATED) [032-S4_project_db_access](032-S4_project_db_access.md): same class
- (RELATED) [063-F1_full_text_search](063-F1_full_text_search.md): cheap opens make searching across chronicles viable
