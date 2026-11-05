# 060-D2_fix_doc_drift

## Top-level docs have drifted from the code

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Low: misleads new contributors, which matters more with several people working. Change risk: none. |
| reach | All contributors |
| effort | S |
| evidence | read in code |
| touches | `README.md`, `ARCHITECTURE.md`, `HOWTO.md`, `docs/storage.md`, `docs/deployment-and-rpc.md` |

### description

| Where | Says | Reality |
| ----- | ---- | ------- |
| `README.md:4`, `:317` | Python 3.10+ | `requires-python = ">=3.12"` |
| `ARCHITECTURE.md:230` | Describes a Search Service | Deleted in Sprint 11 |
| `ARCHITECTURE.md:337`, `docs/storage.md:145` | A reserved `metadata` table exists | Dropped by migration `e5b2f70c31a8` |
| `ARCHITECTURE.md:468` | Implemented tasks: IMPORT, CLEAN, TRANSCRIBE | NORMALIZE and SUMMARIZE exist too |
| `docs/deployment-and-rpc.md:24`, `:58` | Every public coroutine is exposed | Explicit `expose=` lists since Sprint 11 |
| `HOWTO.md:108` | Two features need extras | Five extras exist |

### related tickets

- (RELATED) [012-S14_remove_web_client](012-S14_remove_web_client.md): that ticket rewrites the deployment-mode sections
