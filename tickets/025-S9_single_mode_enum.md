# 025-S9_single_mode_enum

## Replace the three mode vocabularies with one enum

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Medium: it fixes a startup crash. Change risk: low. |
| reach | All startup paths |
| effort | S |
| evidence | reproduced |
| touches | `chronicler/core/config.py`, `chronicler/__main__.py`, `chronicler/core/wizard.py`, `chronicler/desktop/runtime.py`, `chronicler/desktop/main.py`, `chronicler/desktop/views/wizard.py`, `chronicler/desktop/views/settings/view.py`, `tests/chronicler/test_main.py`, `tests/chronicler/core/test_config.py` |

### description

The same idea has three spellings. The CLI takes `desktop`, `server`, `client:desktop`
(`__main__.py:60`, mapped at `:95-102`). Settings stores `desktop:full_stack` and
`desktop:thin_client`, with `None` inferred in `desktop/runtime.py:28-34`.
`SettingsView.is_thin_client` uses `bool(server_url)` (`settings/view.py:54-56`).
Validation and runtime building can therefore disagree.

### proposed fix

1. Add `class Mode(StrEnum)` with `FULL_STACK`, `THIN_CLIENT` and `SERVER`, and type
   `Settings.mode` with it.
2. Accept the old stored values when loading: `desktop:full_stack`, `desktop:thin_client`
   and `client:web`.
3. Add one `Settings.effective_mode` property with the inference from `runtime.py`, used
   by validation, runtime building and `SettingsView`.
4. Reduce the CLI to `desktop` and `server`, and delete `mode_map`.

Done when validation and `build_runtime` cannot reach different answers for the same
settings, and a stored `client:web` configuration with a server URL starts as a thin
client.

### related tickets

- (BLOCKER) [012-S14_remove_web_client](012-S14_remove_web_client.md): removes the `client:web` mode, so there is one fewer to carry
- (BLOCKS) [041-S3_services_bundle](041-S3_services_bundle.md): `build_runtime` is rewritten around the mode enum
- (BLOCKS) [042-S10_console_wizard_to_flags](042-S10_console_wizard_to_flags.md): uses the mode enum
- (BLOCKS) [049-L5_open_folder_thin_client](049-L5_open_folder_thin_client.md): uses `desktop_mode`
- (RELATED) [026-M9_stale_mode_crashes_desktop](026-M9_stale_mode_crashes_desktop.md): closed by 012's stopgap for `client:web`; this ticket replaces the stopgap
