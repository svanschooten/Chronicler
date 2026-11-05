# 058-T6_ui_rendering_checks

## Nothing verifies the real rendered UI

### info

| | |
| --- | --- |
| importance | low |
| danger level | Medium: UI bugs reach users, as four rounds of Sprint 4 fixes showed. Change risk: none. |
| reach | All contributors |
| effort | M |
| evidence | read in code; already noted in `TODO.md:1435` |
| touches | `tests/`, CI |

### description

Views are only tested as control trees. Nothing renders, and the audit did not open the UI
either. So bugs like the view rebuild in the linked ticket can only be found by hand. It
is not yet known what Flet 0.86 offers for testing a rendered app.

### related tickets

- (RELATED) [027-M7_refresh_view_in_place](027-M7_refresh_view_in_place.md): the kind of bug this would catch
