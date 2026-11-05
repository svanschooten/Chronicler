# 045-T5_ruff_rules_and_target

## Tighten Ruff's rules and target version

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: blocking calls can creep into async code. Change risk: low. |
| reach | All contributors |
| effort | S |
| evidence | scanned |
| touches | `pyproject.toml`, `chronicler/core/database_manager.py`, `chronicler/core/file_staging.py`, `chronicler/core/processing/handlers/importing.py`, `normalizing.py`, `chronicler/desktop/views/transcript/export.py` |

### description

`pyproject.toml:87` sets `target-version = "py310"` while the project requires 3.12.
Ruff's `ASYNC` rules flag 9 blocking calls in async functions, and `DTZ` flags 9 naive
`datetime.now()` calls.

### proposed fix

1. Set `target-version = "py312"` and apply the resulting fixes.
2. Enable `ASYNC`, and fix or narrowly suppress the 9 findings with a comment explaining
   why.
3. Consider `DTZ`. Times are stored as naive local values, so moving to UTC means changing
   how they display. Either do that or suppress it with a comment.

Done when `ruff check` passes with the new rules.

### related tickets

- (RELATED) [028-P1_exports_off_event_loop](028-P1_exports_off_event_loop.md): covers the larger blocking calls Ruff cannot see
