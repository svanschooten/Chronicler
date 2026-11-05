# 012-S14_remove_web_client

## Remove the web client

### info

| | |
| --- | --- |
| importance | high |
| danger level | High while it exists: an open proxy to the full API. Change risk: low, it does 3 of 36 operations. |
| reach | Anyone using `chronicler web`, and the `client:web` configuration |
| effort | S |
| evidence | read in code |
| touches | `chronicler/webclient/`, `tests/chronicler/webclient/`, `chronicler/__main__.py`, `chronicler/core/config.py`, `chronicler/core/wizard.py`, `chronicler/core/rpc.py`, `chronicler/core/file_staging.py`, `chronicler/desktop/views/transcript/view.py`, `chronicler/i18n/messages/en.py`, `chronicler/i18n/messages/nl.py`, `Chronicler.spec`, `scripts/pack.sh`, `README.md`, `HOWTO.md`, `ARCHITECTURE.md`, `TODO.md`, `docs/README.md`, `docs/configuration.md`, `docs/deployment-and-rpc.md`, `docs/packaging.md`, `docs/security.md`, `docs/transcript-editing.md`, `tests/chronicler/core/test_config.py`, `test_file_staging.py`, `test_wizard.py`, `test_rpc.py`, `tests/chronicler/test_main.py`, `tests/chronicler/desktop/views/transcript/test_view.py` |

### description

Decision from the audit: remove it for now. The web client is 437 lines, a proxy and a
deferred auth design for 3 API calls: list chronicles, create a chronicle and queue an
import. It is the largest security exposure in the project, and `TODO.md` already calls it
a "much later" concern.

If browser access is wanted later, try Flet's web mode over the thin client first, which
could reuse most of the existing UI. That is untested. The code stays in git history.

### proposed fix

1. Delete `chronicler/webclient/` and its tests.
2. Remove `web` and `client:web` from `__main__.py`, `webclient_main`, the `client:web`
   branch of `validate_for_mode`, and the web option in `core/wizard.py`.
3. Remove `CORSMiddleware` from `core/rpc.py:161-167`. No browser calls the API any more,
   so nothing needs a wildcard origin.
4. Remove the data entry from `Chronicler.spec:11` and `scripts/pack.sh:16`.
5. Remove `_can_go_fullscreen`, whose only reason was this mode (`view.py:477-482`). A
   desktop window can always go fullscreen.
6. Update the docs from four deployment modes to three.

Done when `chronicler web` is rejected by argparse, nothing references `webclient`, and
the suite passes.

### related tickets

- (BLOCKS) [016-H1_server_component_for_binaries](016-H1_server_component_for_binaries.md): only server mode needs to be packaged once the web client is gone
- (BLOCKS) [025-S9_single_mode_enum](025-S9_single_mode_enum.md): removes the `client:web` mode, so there is one fewer to carry
- (BLOCKS) [042-S10_console_wizard_to_flags](042-S10_console_wizard_to_flags.md): removes the web client branch
- (BLOCKS) [062-D1_split_todo](062-D1_split_todo.md): decides what happens to the web client sections
- (CLOSES) [013-H2_web_client_open_proxy](013-H2_web_client_open_proxy.md): the proxy no longer exists
- (CLOSES) [014-M8_web_audio_upload_fails](014-M8_web_audio_upload_fails.md): the page no longer exists
- (RELATED) [053-L9_upload_size_cap](053-L9_upload_size_cap.md): removes the proxy half of this problem
- (RELATED) [060-D2_fix_doc_drift](060-D2_fix_doc_drift.md): that ticket rewrites the deployment-mode sections
