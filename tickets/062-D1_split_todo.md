# 062-D1_split_todo

## TODO.md is a changelog, a roadmap and a design archive at once

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: hard to find what is true. Change risk: none. |
| reach | All contributors |
| effort | S |
| evidence | read in code |
| touches | `TODO.md`, new `CHANGELOG.md`, new `ROADMAP.md`, `docs/` |

### description

`TODO.md` is 1,458 lines. It mixes sprint history, open items and long designs, and it has
drifted: Phase 9 leaves builds and releases unchecked though both exist, PDF, HTML and
summaries are listed as future work though they shipped, `characterDesigner/` is described
as extracted but is not in this repository, and "no source file over about 370 lines" is
no longer true (the largest is 566).

### proposed fix

Move the sprint history to `CHANGELOG.md`, keep open direction in a short `ROADMAP.md`
that links to `tickets/`, and move the live-update design to `docs/`. The browser auth
design can go with the web client.

Done when `TODO.md` is gone and no doc links to it.

The review after wave 4 re-baselined `TODO.md` against the code: marks corrected, open
items pointed at their tickets, and the web client section reduced to the design notes
worth keeping. That makes the split mechanical, but it is still one file doing three
jobs.

### related tickets

- (BLOCKER) [012-S14_remove_web_client](012-S14_remove_web_client.md): decides what happens to the web client sections
