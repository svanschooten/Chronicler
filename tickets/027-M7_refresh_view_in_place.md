# 027-M7_refresh_view_in_place

## A finished task rebuilds the view on screen

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Medium: loses search text, open forms and text being typed. Change risk: medium, UI behaviour cannot be fully tested without rendering. |
| reach | Full-stack desktop, whenever a task finishes |
| effort | M |
| evidence | read in code; not run in the real UI |
| touches | `chronicler/desktop/app.py`, `chronicler/desktop/views/archive/view.py`, `chronicler/desktop/views/tasks.py`, `chronicler/desktop/views/transcript/view.py`, `tests/chronicler/desktop/test_app.py` |

### description

`_on_task_completed` (`app.py:160-178`) calls `update_view`, which constructs a new view.
That resets search text and the hide-completed box, detaches open forms, and leaves
transcript edit mode along with any text typed into the focused field.
`TranscriptView.reload` guards against editing (`view.py:383`), and this path does not.

### proposed fix

Keep the current view object, pass the event to it, and let it refresh its own data:

- `ArchiveView`: `load_chronicles()`, which keeps the query.
- `TasksView`: `load_tasks()`.
- `TranscriptView`: reload the sources, summaries and header, and reload the transcript
  only when not editing.

Done when a task finishing during a search, with a form open, or while editing changes
none of those. Check it in the running app as well as in tests.

### related tickets

- (BLOCKS) [041-S3_services_bundle](041-S3_services_bundle.md): both change how `DesktopApp` holds its views
- (RELATED) [058-T6_ui_rendering_checks](058-T6_ui_rendering_checks.md): the kind of bug this would catch
- (RELATED) [064-F2_progress_and_cancel](064-F2_progress_and_cancel.md): both change how the Tasks view refreshes
