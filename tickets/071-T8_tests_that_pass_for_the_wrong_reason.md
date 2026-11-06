# 071-T8_tests_that_pass_for_the_wrong_reason

## Two tests pass for a reason other than the one they state

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: a regression in these spots would not be caught. Change risk: none. |
| reach | Test suite only |
| effort | XS |
| evidence | reproduced |
| touches | `tests/chronicler/desktop/test_reveal.py`, `tests/chronicler/core/services/test_linking.py` |

### description

Found while reviewing 003-T1 and 006-C3.

- The two WSL tests in `test_reveal.py` (`:66`, `:77`) patch `sys.platform` to
  `"linux"`. That patch changes nothing: with WSL detected, `file_manager_command`
  returns `explorer.exe` whatever the platform. The single-backslash `stdout` is what
  fixed the Windows failure. It also patches `sys.platform` for the whole interpreter
  while the test runs.
- `test_linking.py:191` checks the speaker registry through a second session, to prove
  that registering a speaker commits. It still passes with the commit removed, because
  `refresh_speaker_count` later commits the shared session through
  `chronicle_repository.update`. The repository tests in
  `test_known_speaker_repository.py` do catch that regression.

### proposed fix

- Remove the `sys.platform` patches.
- In `test_linking.py`, either assert something the linking flow alone guarantees, or
  drop the second-session read and rely on the repository tests, with a comment saying
  so.

Done when each remaining assertion fails if the behaviour its name describes is removed.

### related tickets

- (RELATED) [003-T1_windows_test_portability](003-T1_windows_test_portability.md): introduced the WSL test change
- (RELATED) [006-C3_speaker_registry_commit](006-C3_speaker_registry_commit.md): introduced the second-session reads
