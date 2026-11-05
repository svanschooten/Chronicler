# 005-T3_windows_in_ci

## CI never runs on Windows, a platform you ship to

### info

| | |
| --- | --- |
| importance | high |
| danger level | Medium: Windows-only bugs surface after merge, as the file-deletion bug did. Change risk: low. |
| reach | All contributors, Windows users |
| effort | XS |
| evidence | read in code |
| touches | `.github/workflows/continuous-integration-workflow.yml` |

### description

The test matrix is `os: [ubuntu-latest]` (`continuous-integration-workflow.yml:187`),
while releases build for Windows and the project is developed there. With several people
working in parallel, this is the check that keeps Windows from regressing.

### related tickets

- (BLOCKER) [003-T1_windows_test_portability](003-T1_windows_test_portability.md): the 11 Windows failures must be fixed first
- (BLOCKER) [004-S12_ci_and_install_cleanup](004-S12_ci_and_install_cleanup.md): needs the shared setup step, and both edit the same workflow
