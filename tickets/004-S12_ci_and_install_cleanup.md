# 004-S12_ci_and_install_cleanup

## CI and install files carry a lot of avoidable text

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Low: slower reviews, and no gate on formatting. Change risk: low. |
| reach | All contributors |
| effort | S |
| evidence | measured |
| touches | `.github/workflows/continuous-integration-workflow.yml`, `requirements*.txt`, `README.md`, `docs/testing.md` |

### description

- About 85 lines (`continuous-integration-workflow.yml:91-178`) maintain an advisory
  formatting comment on PRs. The reason given is that the tree has drifted, but all 215
  files now pass `ruff format --check`.
- The venv restore and fallback install is written out three times (`:28-42`, `:64-81`,
  `:199-213`).
- `requirements.txt`, `requirements-dev.txt` and `requirements-server.txt` wrap one
  command, and `requirements.txt` adds unpinned duplicates of the `server` extra.

### proposed fix

1. Replace the advisory steps with one blocking `ruff format --check chronicler tests`.
2. Move setup into a composite action (or use `uv`), so each job has one setup step that
   also works on Windows.
3. Delete the three requirements files. CI and the docs use `pip install -e
   ".[dev,server]"`.
4. Update `README.md` and `docs/testing.md:53-55`, which still call formatting advisory.

Done when CI passes with formatting as a gate and the workflow has one setup definition.

### related tickets

- (BLOCKER) [001-C1_sqlalchemy_asyncio_extra](001-C1_sqlalchemy_asyncio_extra.md): CI reinstalls dependencies as soon as its cache key changes
- (BLOCKS) [005-T3_windows_in_ci](005-T3_windows_in_ci.md): needs the shared setup step, and both edit the same workflow
- (BLOCKS) [044-T4_extras_ci_job](044-T4_extras_ci_job.md): edits the same workflow, and reuses its setup step
