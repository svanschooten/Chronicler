# 033-L1_shared_session_panel_loads

## Three panel loads share one database session

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: latent. Reproduced only with an empty connection pool. Change risk: none beyond the linked ticket. |
| reach | Full-stack desktop, transcript view |
| effort | none beyond the linked ticket |
| evidence | reproduced with an empty pool |
| touches | `chronicler/desktop/views/transcript/view.py:361-363`, `chronicler/core/services/transcript_service.py:159-163` |

### description

`did_mount` schedules three loads over one scope's archive session, which
`ARCHITECTURE.md:442-444` warns against. Each calls `_project_path`, which queries that
session.

With an empty connection pool, 150 of 200 calls raised `This session is provisioning a new
connection; concurrent operations are not permitted`. The normal path escapes because
`_build_view` has already queried on that session, and 600 calls succeeded with a warm
pool.

### related tickets

- (CLOSED BY) [032-S4_project_db_access](032-S4_project_db_access.md): location lookups get their own session
