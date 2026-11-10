# 070-T7_dependabot_config

## Dependabot misses the shared setup action and opens floor-only PRs

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: one action pin drifts, and PRs pile up that change nothing CI installs. Change risk: very low. |
| reach | Maintainers |
| effort | XS |
| evidence | read in code |
| touches | `.github/dependabot.yml` |

### description

Found while reviewing 004-S12. The `github-actions` entry only covers `directory: "/"`,
which Dependabot reads as `.github/workflows/`. Since 004, `actions/setup-python` is also
pinned in `.github/actions/setup/action.yml`, which nothing updates, so that copy will
fall behind the ones in the workflows.

The `pip` entry uses the default strategy, which raises lower bounds such as
`aiosqlite>=0.20` to `>=0.22.1`. CI installs the newest allowed version anyway, so these
PRs change nothing that is tested. Five are open (#19, #20, #24, #25, #26), their CI
predates the current workflow, and #19 and #20 conflict with master.

### proposed fix

1. Use `directories: ["/", "/.github/actions/*"]` for `github-actions`.
2. Set `versioning-strategy: increase-if-necessary` for `pip`, so Dependabot only opens a
   PR when a new release falls outside the allowed range.
3. Close #19, #20, #24, #25 and #26, or comment `@dependabot rebase` on any worth keeping.

Done when Dependabot lists `.github/actions/setup/action.yml` among its update targets.

### related tickets

- (RELATED) [004-S12_ci_and_install_cleanup](004-S12_ci_and_install_cleanup.md): added the composite action
