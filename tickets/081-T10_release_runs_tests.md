# 081-T10_release_runs_tests

## Release builds do not run the tests

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: a release from a tag CI never ran on ships untested. Change risk: very low. |
| reach | Maintainers, and everyone downloading a release |
| effort | XS |
| evidence | read in code |
| touches | `.github/workflows/release-workflow.yml` |

### description

Found in the review after wave 4.

`release-workflow.yml` resolves the version, then builds and uploads binaries. Nothing in
it runs the quality checks or the tests. Releases are normally cut from `master`, which
CI gates, but `workflow_dispatch` accepts any tag, and a tag can point at a commit CI
never saw.

### proposed fix

Add a job that reuses `.github/actions/setup` and runs ruff, mypy and pytest, and make
`pack` and `runtime` depend on it, alongside `version`.

Done when a release run with a failing test produces no binaries.

### related tickets

- (RELATED) [059-S15_retire_pyinstaller](059-S15_retire_pyinstaller.md): edits the same workflow
- (RELATED) [044-T4_extras_ci_job](044-T4_extras_ci_job.md): its extras job could run here too
