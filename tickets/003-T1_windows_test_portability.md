# 003-T1_windows_test_portability

## 11 tests fail on Windows, and test isolation does not hold there

### info

| | |
| --- | --- |
| importance | high |
| danger level | Medium: Windows developers have no green baseline, and tests resolve their real config paths. Change risk: very low. |
| reach | Everyone running tests on Windows |
| effort | S |
| evidence | reproduced |
| touches | `tests/conftest.py`, `tests/chronicler/core/test_config.py`, `tests/chronicler/core/test_wizard_defaults.py`, `tests/chronicler/core/services/test_transcript_export.py`, `tests/chronicler/desktop/test_reveal.py` |

### description

The suite gives 1,251 passed, 2 skipped and 11 failed on Windows with Python 3.12. All 11
are test portability problems rather than product bugs:

| Tests | Cause | Where |
| ----- | ----- | ----- |
| 7 | `HOME` is ignored by `Path.home()` and `expanduser()` on Windows, which read `USERPROFILE` | `test_config.py` (explicit file expanded, save to home config, is_config_initialized, 3 in `TestNestedSections`), `test_wizard_defaults.py` (home shorthand) |
| 1 | Hand-built JSON contains an unescaped Windows path | `test_load_settings` (`test_config.py:183`) |
| 1 | `read_text()` uses cp1252 on the UTF-8 example | `test_transcript_export.py:38` |
| 1 | `chmod` does not make a directory unwritable on Windows | `test_workspace_validation` |
| 1 | Path escaping differs in the WSL case | `test_reveal.py:71` |

The first row is also a safety problem. The fixtures in `tests/conftest.py:47` and
`test_config.py:19` only set `HOME`, so on Windows `Settings().save_path()` resolves the
developer's real `AppData` location. No real files appeared during the audit runs, but
nothing prevents it.

### proposed fix

- Set `USERPROFILE` as well as `HOME` in both fixtures.
- Use `json.dumps` in `test_load_settings`.
- Pass `encoding="utf-8"` in `test_transcript_export.py:38`.
- Skip the `chmod` assertion on Windows, or test by writing a probe file (see the related
  workspace validation ticket).
- Patch the platform consistently in the WSL test.

Done when `pytest` is fully green on Windows and no test resolves a path outside
`tmp_path`.

### related tickets

- (BLOCKER) [001-C1_sqlalchemy_asyncio_extra](001-C1_sqlalchemy_asyncio_extra.md): needs a working install
- (BLOCKS) [005-T3_windows_in_ci](005-T3_windows_in_ci.md): the 11 Windows failures must be fixed first
- (RELATED) [055-L11_workspace_validation](055-L11_workspace_validation.md): that ticket deals with this method's Windows test
