# 080-T9_warning_free_tests

## The test suite is not warning-free under coverage

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: warnings that hid a real session leak before are back, unnoticed. Change risk: none. |
| reach | Test suite only |
| effort | XS |
| evidence | reproduced |
| touches | `tests/`, `pyproject.toml` |

### description

Found in the review after wave 4.

`TODO.md` records the suite as warning-free since Sprint 11, and a plain `pytest` run is.
Under `--cov`, which is how CI runs it, 4 `ResourceWarning: unclosed database` warnings
appear. Which test reports them changes from run to run, because they surface whenever
the garbage collector finds the connection. Seen so far:
`test_remote.py::test_remote_proxy_serializes_uuid_arguments`,
`test_rpc.py::test_rpc_server_and_remote_proxy` and
`test_rpc.py::test_upload_rejects_oversized_file`. That points at RPC and remote tests
that build a `DatabaseManager` and never call `close_all()`.

With `-W default`, more appear: unclosed `aiosqlite` connections in
`test_audio_source_repository.py` and `test_project_migrations.py`, and an unclosed
file in `test_workspace_lock.py::test_a_killed_process_does_not_block_the_next_start`.

pytest-asyncio also warns that `asyncio_default_fixture_loop_scope` is unset, and its
default is changing.

### proposed fix

1. Run once with `PYTHONTRACEMALLOC=20` and `-W default` to find where each connection is
   opened, and close or dispose it in the fixture.
2. Set `asyncio_default_fixture_loop_scope = "function"` in `pyproject.toml`.
3. Once clean, make `ResourceWarning` an error in `filterwarnings`, so a new leak fails CI.

Done when `pytest --cov=chronicler -W default` reports no warnings.

### related tickets

- (RELATED) [071-T8_tests_that_pass_for_the_wrong_reason](071-T8_tests_that_pass_for_the_wrong_reason.md): the other test-quality item
