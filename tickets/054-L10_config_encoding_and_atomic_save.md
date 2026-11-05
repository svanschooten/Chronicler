# 054-L10_config_encoding_and_atomic_save

## Config files can be misread and overwritten

### info

| | |
| --- | --- |
| importance | low |
| danger level | Medium: a hand-edited config can be replaced by the wizard. Change risk: low. |
| reach | Mostly Windows users who edit the file by hand |
| effort | XS |
| evidence | read in code |
| touches | `chronicler/core/config.py`, `tests/chronicler/core/test_config.py` |

### description

`_read_config` uses `read_text()` with the locale encoding (`config.py:67-68`). On
Windows, a hand-edited UTF-8 file can fail to decode. Every setting is then ignored with a
warning, and the wizard overwrites the file. `save()` (`config.py:154`) is also not
atomic, so a crash mid-write truncates it.

### proposed fix

Read and write as UTF-8, and save through a temp file and `os.replace`. If a file exists
but cannot be parsed, keep a `.bak` copy before anything overwrites it.

Done when a UTF-8 config with non-ASCII text loads on Windows.

### related tickets

- (BLOCKER) [015-H3_protect_api_keys](015-H3_protect_api_keys.md): both change `Settings.save`
