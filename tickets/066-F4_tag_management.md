# 066-F4_tag_management

## Tag management

### info

| | |
| --- | --- |
| importance | low |
| danger level | None: a missing feature the README lists. Change risk: low. |
| reach | All modes |
| effort | M |
| evidence | read in code |
| touches | `chronicler/core/sqlite/chronicle_repository.py`, `chronicler/core/services/chronicle_service.py`, `chronicler/desktop/forms.py`, `chronicler/desktop/views/archive/` |

### description

Only the system tags Transcript and Summarized can exist today. Users cannot add tags or
filter by them, though the README lists tags as part of a Chronicle. `tags.color` exists
but nothing uses it, and nothing removes tags that no chronicle uses any more.

### related tickets

- (BLOCKER) [029-S1_remove_dead_code](029-S1_remove_dead_code.md): removes `TagRepository`, which this should not revive
- (RELATED) [029-S1_remove_dead_code](029-S1_remove_dead_code.md): keep `tags.color` for that ticket to decide on
