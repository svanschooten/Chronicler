# 063-F1_full_text_search

## Full-text transcript search

### info

| | |
| --- | --- |
| importance | medium |
| danger level | None: a missing feature, and the product's main promise. Change risk: medium, adds a migration. |
| reach | All users |
| effort | L |
| evidence | read in code; open-cost measured |
| touches | `chronicler/core/project_database.py`, new migration in `chronicler/migrations/project/`, `chronicler/core/sqlite/transcript_repository.py`, `chronicler/core/services/`, `chronicler/desktop/views/archive/view.py`, `chronicler/desktop/views/transcript/` |

### description

The tagline says "Discover knowledge", and search cannot find a word anyone said. Search
today covers title, description and tags only.

Transcript lines live in per-chronicle databases, so workspace search needs a design.
`ARCHITECTURE.md:527-530` names the choice: a fan-out, or an index to keep in sync.

### proposed fix

1. Add an FTS5 table in each `project.db`, kept in sync with triggers, and backfill it in
   the migration.
2. For the whole workspace, use a plain fan-out. A unit of work took about 2 ms with
   `NullPool`, so hundreds of chronicles should take around a second before query time,
   with no index to keep in sync. A database's first open in a session costs more, up to
   44 ms when it runs every migration, so show results as they arrive.
3. Add it to the archive search box, and add find-in-transcript to the chronicle view.

Done when a search for a spoken phrase finds the chronicle and the line.

### related tickets

- (BLOCKER) [032-S4_project_db_access](032-S4_project_db_access.md): uses the project database helper
- (BLOCKER) [031-S5_nullpool_project_engines](031-S5_nullpool_project_engines.md): needs cheap opens for the fan-out
- (BLOCKER) [020-M3_explicit_timing_flag](020-M3_explicit_timing_flag.md): same migration chain, so this rebases on it
- (RELATED) [031-S5_nullpool_project_engines](031-S5_nullpool_project_engines.md): cheap opens make searching across chronicles viable
