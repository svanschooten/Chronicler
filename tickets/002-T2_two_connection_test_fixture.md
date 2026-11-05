# 002-T2_two_connection_test_fixture

## Tests cannot simulate a locked database

### info

| | |
| --- | --- |
| importance | high |
| danger level | Medium: the bugs in the worker and speaker registry stay invisible to CI. Change risk: very low. |
| reach | Test suite only |
| effort | XS |
| evidence | read in code |
| touches | `tests/conftest.py`, `chronicler/core/database_manager.py` |

### description

The shared `async_session` fixture (`tests/conftest.py:23-34`) is one in-memory
connection, where a lock cannot occur. No test makes the worker or a view wait on another
connection's write lock. The only "database is locked" in a view test is a stubbed error
message (`test_editor.py:148`).

Several tickets need the same setup, so it should land once, before they start. Otherwise
each adds its own version to `conftest.py`.

### proposed fix

Add a fixture that gives a test a real file-backed workspace and two independent sessions
on `chronicler.db`.

SQLite's default wait is 5 seconds, which would make each contention test slow. Add an
optional `busy_timeout: float = 5.0` argument to `DatabaseManager`, passed as
`connect_args={"timeout": ...}` to its engines, and have the fixture use about 0.2
seconds.

Done when a sample test shows a second writer getting `OperationalError` in under a second
while the first session holds a flushed, uncommitted write.

### related tickets

- (BLOCKER) [001-C1_sqlalchemy_asyncio_extra](001-C1_sqlalchemy_asyncio_extra.md): needs a working install
- (BLOCKS) [006-C3_speaker_registry_commit](006-C3_speaker_registry_commit.md): uses the two-connection fixture
- (BLOCKS) [007-C2_worker_session_per_step](007-C2_worker_session_per_step.md): uses the two-connection fixture
