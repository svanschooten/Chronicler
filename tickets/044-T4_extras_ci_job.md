# 044-T4_extras_ci_job

## Optional extras never run in CI

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Medium: normalization code is effectively untested in CI. Change risk: very low. |
| reach | All contributors |
| effort | S |
| evidence | measured |
| touches | `.github/workflows/continuous-integration-workflow.yml` |

### description

CI installs no extras. Coverage of `normalizer.py` is 19% without them and 86% with them,
and `handlers/normalizing.py` goes from 38% to 95%. With the transcription and
normalization locks installed, 30 more tests pass.

### proposed fix

Add a job that installs `base.lock` and the component locks with `--require-hashes
--no-deps`, adds the test tools, installs PortAudio on Linux, and runs the suite.

Installing every lock at once hides a component that is missing a dependency of its
own: numpy reaches normalization only through the transcription lock (see 067). So also
install each component lock alone on top of `base.lock` and import its module.

Done when that job runs with no skips caused by missing extras, and each component
imports with only its own lock installed.

### related tickets

- (RELATED) [067-M11_normalization_extra_numpy](067-M11_normalization_extra_numpy.md): the bug a combined install hides
- (BLOCKER) [004-S12_ci_and_install_cleanup](004-S12_ci_and_install_cleanup.md): edits the same workflow, and reuses its setup step
- (BLOCKS) [057-P6_normalization_single_pass](057-P6_normalization_single_pass.md): changing this safely needs the audio tests running in CI
- (RELATED) [057-P6_normalization_single_pass](057-P6_normalization_single_pass.md): needs real audio tests to change safely
