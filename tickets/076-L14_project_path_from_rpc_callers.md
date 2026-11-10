# 076-L14_project_path_from_rpc_callers

## Remote callers can point a chronicle at any path on the server

### info

| | |
| --- | --- |
| importance | low |
| danger level | Medium for an exposed server: anyone holding the API key can create folders, place uploaded files and run migrations wherever the server process can write. Low for a private one. Change risk: low. |
| reach | Server |
| effort | S |
| evidence | read in code |
| touches | `chronicler/core/services/chronicle_service.py`, `chronicler/core/config.py`, `tests/chronicler/core/services/test_linking.py`, `tests/chronicler/server/test_rpc_routing.py`, `docs/security.md` |

### description

Found in the review after wave 4.

Three exposed routes accept a `project_path` from the caller: `create_chronicle`,
`link_external_chronicle` and `update_chronicle`. `docs/security.md` listed only the
first as deliberately open, and understated what follows from it:

- `add_audio_source` creates `<parent of project_path>/sources/` and moves an uploaded
  file into it, so a caller can write files into any directory the server can.
- A clean creates `<parent>/snapshots/` beside it.
- Opening the chronicle runs the project migrations against whatever SQLite file the path
  names, adding tables to it.
- `export_zip` with sources reads every file in `<parent>/sources/`.

All of this needs the API key, which is the server's only boundary.

### proposed fix

1. Add a server setting naming the directories linked chronicles may live in, empty by
   default, and confine `project_path` to them with `confine_to_directory`.
2. Full-stack mode keeps linking anywhere: there the caller is the machine's own user.
3. Stop `update_chronicle` accepting `project_path` (see 075).
4. Update the open-items list in `docs/security.md`.

Done when a remote `create_chronicle` or `link_external_chronicle` with a path outside the
allowed directories is refused, and full-stack linking still works.

### related tickets

- (RELATED) [075-L13_edit_drops_computed_duration](075-L13_edit_drops_computed_duration.md): narrows `update_chronicle`
- (RELATED) [072-M13_failed_link_leaves_chronicle](072-M13_failed_link_leaves_chronicle.md): hides *Link* on thin clients, its only UI caller over RPC
- (RELATED) [053-L9_upload_size_cap](053-L9_upload_size_cap.md): the other remaining server hardening item
