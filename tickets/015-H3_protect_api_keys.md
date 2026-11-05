# 015-H3_protect_api_keys

## The API key is logged, and secrets from the environment get saved to disk

### info

| | |
| --- | --- |
| importance | high |
| danger level | High: credentials in logs and in plain files. Change risk: low. |
| reach | Server operators, and anyone configuring through environment variables |
| effort | S |
| evidence | reproduced (environment write); read in code (log line) |
| touches | `chronicler/server/main.py`, `chronicler/core/config.py`, `tests/chronicler/core/test_config.py` |

### description

`server/main.py:51` logs the full API key at INFO on every start.

`Settings.save()` (`config.py:151-157`) writes the whole merged configuration, so
`CHRONICLER_API_KEY` from the environment lands in the YAML file the first time anything
saves. Toggling dark mode is enough. The config file also holds `llm.api_key` and gets no
restrictive file mode.

### proposed fix

1. Delete the log line. If operators need a confirmation, log that a key is configured, or
   the last 4 characters.
2. In `save()`, leave out values that came from the environment, keeping whatever the file
   already had for them. This includes nested variables such as `CHRONICLER_LLM__API_KEY`.
3. Set mode 600 on the config file on POSIX.

Done when a test with `CHRONICLER_API_KEY` set finds no secret in the saved file, and
server startup logs contain no key.

### related tickets

- (BLOCKS) [054-L10_config_encoding_and_atomic_save](054-L10_config_encoding_and_atomic_save.md): both change `Settings.save`
