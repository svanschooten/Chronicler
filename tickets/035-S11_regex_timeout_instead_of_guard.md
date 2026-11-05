# 035-S11_regex_timeout_instead_of_guard

## Replace the regex guard with a real timeout

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: it rejects ordinary patterns and bounds nothing. Change risk: low, adds one dependency. |
| reach | Custom import patterns and cleaning patterns. About 120 lines |
| effort | S |
| evidence | reproduced |
| touches | `chronicler/core/processing/regex_guard.py`, `chronicler/core/processing/importers.py`, `chronicler/core/processing/cleaners.py`, `chronicler/core/config_sections.py`, `chronicler/core/services/task_service.py`, `pyproject.toml`, `scripts/runtime/locks/`, `Chronicler.spec`, `scripts/pack.sh`, `docs/security.md`, `HOWTO.md` |

### description

`regex_guard.py` is 127 lines on the private `re._parser`, which also forces a PyInstaller
hidden import. It is not a CPU bound, by its own docs (`docs/security.md:67-71`). It also
rejects ordinary patterns: `^(\w+( \w+)*):(.*)$`, for speaker names with spaces, is
refused and matched in 0.11 ms.

### proposed fix

Use the `regex` package with `timeout=` for user-supplied patterns, keeping the
500-character limit. A timeout fails the task with a clear message. This is a real bound,
which the current check cannot give.

Regenerate the locks, remove the hidden import, and update the docs and the note in
`TODO.md` about a per-task CPU timeout.

Done when `(a+)+$` against an adversarial line stops at the timeout, and the pattern above
works.

### related tickets

- none
