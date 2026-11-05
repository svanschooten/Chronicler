# 042-S10_console_wizard_to_flags

## Replace the console wizard with flags

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: maintenance cost only. Change risk: low. |
| reach | Server setup. About 120 lines |
| effort | S |
| evidence | read in code |
| touches | `chronicler/core/wizard.py`, `chronicler/__main__.py`, `chronicler/desktop/views/wizard.py`, `tests/chronicler/core/test_wizard.py`, `test_wizard_defaults.py`, `HOWTO.md`, `docs/configuration.md` |

### description

`core/wizard.py` is 197 lines and a class hierarchy to ask 3 or 4 questions, next to the
428-line Flet wizard. Once the web client is gone, only server mode uses it.

### proposed fix

Add `chronicler server --workspace PATH --api-key KEY`, with environment variables as an
alternative. If a value is missing and stdin is a terminal, ask briefly. Otherwise exit
with a message naming the flag. If no key is given, generate one and print it once.

Keep `LANGUAGE_NAMES`, `default_workspace_path` and `supported_languages`, which the Flet
wizard imports.

Done when `chronicler server` can be configured unattended.

### related tickets

- (BLOCKER) [012-S14_remove_web_client](012-S14_remove_web_client.md): removes the web client branch
- (BLOCKER) [025-S9_single_mode_enum](025-S9_single_mode_enum.md): uses the mode enum
