# 035-S11_regex_timeout_instead_of_guard

## Replace the regex guard with a real timeout, so a pattern cannot freeze the app

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Medium: an ordinary-looking pattern freezes the desktop window, or stalls every client of a server, for seconds to minutes. The guard also rejects ordinary patterns. Change risk: low, adds one dependency. |
| reach | Custom import patterns and cleaning patterns. Full stack (the UI freezes) and server (every request waits). About 120 lines |
| effort | S |
| evidence | reproduced |
| touches | `chronicler/core/processing/regex_guard.py`, `chronicler/core/processing/importers.py`, `chronicler/core/processing/cleaners.py`, `chronicler/core/processing/handlers/importing.py`, `chronicler/core/processing/handlers/cleaning.py`, `chronicler/core/config_sections.py`, `chronicler/core/services/task_service.py`, `pyproject.toml`, `scripts/runtime/locks/`, `Chronicler.spec`, `scripts/pack.sh`, `docs/security.md`, `HOWTO.md` |

### description

`regex_guard.py` is 127 lines on the private `re._parser`, which also forces a PyInstaller
hidden import. It is not a CPU bound, by its own docs (`docs/security.md:67-71`). It also
rejects ordinary patterns: `^(\w+( \w+)*):(.*)$`, for speaker names with spaces, is
refused and matched in 0.11 ms, and so is `^([A-Z][a-z]+(?: [A-Z][a-z]+)*):\s*(.*)$`
for "Firstname Lastname:".

The review after wave 4 found the other half: it accepts patterns that backtrack
polynomially, and those run on the event loop.

| Accepted pattern | Input | Time with `re` |
| ---------------- | ----- | -------------- |
| `^\s*(.*?)\s*:\s*(.*?)\s*$` | one 3,001-character line with no colon | 11.3 s |
| `\s*\s*\s*\s*\s*\s*x` | 60 spaces | 4.4 s. 120 did not finish in 100 s |

The first is a natural "trim and split on colon" pattern.

`handle_import` calls `importer.parse` (`handlers/importing.py:43`) and `handle_clean`
calls `TranscriptCleaner.clean` (`handlers/cleaning.py:138`) directly in the async
handler. In full-stack mode the worker shares the Flet UI's event loop
(`desktop/app.py:122`), and in server mode every request's. Moving the call to
`asyncio.to_thread` alone does **not** help: `re` holds the GIL while it backtracks.
Measured, a 5-second match in a worker thread stalled the event loop for 5.04 s.

The `regex` package behaves differently. Every pattern above, and the textbook
catastrophic ones (`(a+)+$`, `(x+x+)+y`, `^(a|a?)+$`, `(.*a){20}`), finished in under
10 ms with it, in a worker thread, with the event loop never stalled more than 10 ms. A
pattern slow enough to exercise its `timeout=` was not found, so that part is untested.

### proposed fix

1. Use the `regex` package with `timeout=` for user-supplied patterns, keeping the
   500-character limit. A timeout fails the task with a clear message. This is a real
   bound, which the current check cannot give.
2. Run parsing and cleaning with `asyncio.to_thread`, matching with `concurrent=True` so
   `regex` releases the GIL. A long but legitimate import then no longer blocks the
   window either.

Regenerate the locks, remove the hidden import, and update the docs and the note in
`TODO.md` about a per-task CPU timeout.

Done when `(a+)+$` against an adversarial line stops at the timeout or finishes, the two
patterns above work, and a test with a slow pattern shows the event loop still running
during an import.

### related tickets

- (RELATED) [028-P1_exports_off_event_loop](028-P1_exports_off_event_loop.md): the same treatment for exports
- (RELATED) [045-T5_ruff_rules_and_target](045-T5_ruff_rules_and_target.md): Ruff's `ASYNC` rules cannot see CPU-bound calls like these
