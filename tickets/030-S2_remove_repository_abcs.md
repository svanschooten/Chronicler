# 030-S2_remove_repository_abcs

## Remove the repository interfaces

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Low: maintenance cost only. Change risk: low. |
| reach | Internal. About 240 lines |
| effort | S |
| evidence | read in code |
| touches | `chronicler/core/repositories.py`, `chronicler/core/sqlite/`, `chronicler/core/local_container.py`, `chronicler/core/services/`, `chronicler/core/workers.py`, `chronicler/core/processing/handlers/base.py`, `tests/chronicler/core/services/test_task_service.py`, `test_chronicle_service.py`, `tests/chronicler/server/test_rpc_routing.py`, `tests/chronicler/core/test_rpc.py`, `ARCHITECTURE.md`, `docs/dependency-injection.md` |

### description

`repositories.py` is 241 lines with 45 abstract methods, one implementation each.
`SQLiteSummaryRepository` has no interface and works fine. Seven modules import the SQLite
classes directly, so the interfaces only cover half of the storage. Remote operation
already works at the service level, so no second backend is planned.

The abstract bodies also count as uncovered lines (70% on that file).

### proposed fix

Delete `repositories.py` and annotate with the concrete classes. `Container` can
auto-build them, which removes four registrations and their `# type:
ignore[type-abstract]`, and with them the typing item in `TODO.md`. If a second backend
ever appears, add a `Protocol` then.

Done when `repositories.py` is gone and mypy and the tests pass.

### related tickets

- (BLOCKER) [029-S1_remove_dead_code](029-S1_remove_dead_code.md): removes the unused methods first
- (BLOCKS) [041-S3_services_bundle](041-S3_services_bundle.md): removes the factory registrations this replaces
