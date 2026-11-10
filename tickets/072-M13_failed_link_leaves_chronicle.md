# 072-M13_failed_link_leaves_chronicle

## A failed link leaves a broken chronicle, and Link cannot work on a thin client

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Medium: every Link on a thin client adds a chronicle that cannot be opened, and a wrong file does the same on any client. Change risk: low. |
| reach | All modes. Every Link on a thin client |
| effort | S |
| evidence | reproduced |
| touches | `chronicler/core/services/chronicle_service.py`, `chronicler/core/database_manager.py`, `chronicler/desktop/operations.py`, `chronicler/desktop/views/archive/view.py`, `chronicler/i18n/messages/`, `tests/chronicler/core/services/test_linking.py`, `tests/chronicler/desktop/views/archive/test_view.py`, `docs/storage.md` |

### description

Found in the review after wave 4.

`link_external_chronicle` (`chronicle_service.py:53-64`) saves the chronicle row first,
then reads the file in `hydrate_from_project`. When reading fails, the row stays. Run
against the real services:

| Linked path | Error | Chronicles |
| ----------- | ----- | ---------- |
| A path that does not exist | `FileNotFoundError` | 1 → 2 |
| A text file named `project.db` | `DatabaseError: file is not a database` | 2 → 3 |

Opening such a chronicle raises the same error again. Only *Delete* removes it.

On a thin client the picker in `operations.link_chronicle` (`operations.py:135-139`)
returns a path on the client's machine, and the server looks for it on its own disk. So
Link on a thin client always ends as the first row above. This is the same cause as
049, where *Open folder* opens a server path on the client.

The message from `ensure_project_available` (`database_manager.py:45-48`) says the
database "no longer exists", which is wrong for a path that never existed.

A `project.db` written by a newer Chronicler fails here too. See 074.

### proposed fix

1. In `link_external_chronicle`, check that the path is a file before creating anything.
   If hydrating fails anyway, delete the row and raise one error that names the path and
   the reason: not found, not a Chronicler database, or made by a newer version.
2. Hide *Link* on a thin client using `desktop_mode`, the way 049 hides *Open folder*.
   Linking a file on the server from a thin client would need a server-side file browser,
   which is out of scope.
3. Word the missing-file message so it does not claim the file once existed.

Done when a failed link leaves the chronicle count unchanged and says why, and *Link* is
absent on a thin client.

### related tickets

- (RELATED) [049-L5_open_folder_thin_client](049-L5_open_folder_thin_client.md): same thin-client cause, and the same way of hiding the action. Take them together
- (RELATED) [074-A2_schema_versions_for_shared_chronicles](074-A2_schema_versions_for_shared_chronicles.md): a newer database is one of the failures this reports
- (RELATED) [076-L14_project_path_from_rpc_callers](076-L14_project_path_from_rpc_callers.md): limits what a remote caller can link
