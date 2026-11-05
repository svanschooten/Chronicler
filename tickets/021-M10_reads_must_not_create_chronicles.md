# 021-M10_reads_must_not_create_chronicles

## Reading an unknown chronicle creates it on disk

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Medium: orphan folders, and a missing linked file silently becomes a new empty database. Change risk: low. |
| reach | All modes. Over the API, any authenticated client can create folders and databases |
| effort | S |
| evidence | reproduced |
| touches | `chronicler/core/database_manager.py`, `chronicler/core/services/transcript_service.py`, `chronicler/core/processing/handlers/base.py` |

### description

`get_transcript` with a random UUID returns an empty list and creates
`chronicles/<uuid>/project.db`, with no chronicle row. `_project_engine` creates the
folder and migrates (`database_manager.py:107-116`), and `sources_path_for` makes
directories on reads (`:75-76`).

From the code, a task finishing after its chronicle was deleted does the same, leaving an
orphan folder. A linked chronicle whose file has moved would silently get a new, empty
`project.db` at the old path.

### proposed fix

1. In `TranscriptService._get_repository` and `HandlerBase.project_session`, raise
   `LookupError` when the chronicle has no row.
2. For a linked chronicle, raise if its `project_path` no longer exists.
3. Split `sources_path_for` into a pure path lookup and an explicit create, used only when
   writing audio. `_on_disk` must handle a missing folder.

Done when `get_transcript` with an unknown ID raises and creates nothing, and a normal
chronicle still gets its database on first use.

### related tickets

- (BLOCKS) [032-S4_project_db_access](032-S4_project_db_access.md): changes how databases get created
- (RELATED) [046-L2_rpc_error_mapping](046-L2_rpc_error_mapping.md): that ticket turns this `LookupError` into a 404
