# 057-P6_normalization_single_pass

## Normalization decodes the file three times

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: slower normalization. Change risk: low. |
| reach | Normalization users |
| effort | S |
| evidence | read in code; not measured |
| touches | `chronicler/core/processing/normalizer.py` |

### description

`normalize_audio` calls `measure_dbfs` before and after (`normalizer.py:151,189`), which
decodes the whole file two extra times for a report. Inside it, `frame.to_ndarray()` runs
twice per frame (`:120,123`).

### proposed fix

Compute both levels from the frames the main pass already handles, and call `to_ndarray`
once.

Done when the reported levels match today's within a small tolerance on real audio.

### related tickets

- (BLOCKER) [044-T4_extras_ci_job](044-T4_extras_ci_job.md): changing this safely needs the audio tests running in CI
- (RELATED) [044-T4_extras_ci_job](044-T4_extras_ci_job.md): needs real audio tests to change safely
