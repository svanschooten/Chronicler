# 067-M11_normalization_extra_numpy

## The normalization extra does not install numpy, which normalizing needs

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Medium: normalizing fails, saying a component is missing when it is installed. Change risk: very low. |
| reach | The embedded-runtime build with only the normalization component, and source installs of `chronicler[normalization]` without `transcription` |
| effort | XS |
| evidence | reproduced |
| touches | `pyproject.toml`, `chronicler/core/extras.py`, `chronicler/core/processing/normalizer.py`, `scripts/runtime/locks/`, `docs/optional-extras.md` |

### description

`measure_dbfs` imports `numpy` (`normalizer.py:107`). The comment says numpy "ships with
the normalization extra, via PyAV's wheel", but `av` declares no dependencies, and the
`normalization` extra lists only `av` (`pyproject.toml:55-57`). `EXTRAS["normalization"]`
in `extras.py:44-50` gives the same requirement and checks only for the `av` module, so
the in-app install prompt installs the same incomplete set and then reports it present.

In the embedded runtime, numpy is only in `component-transcription.lock`. Someone who
installs normalization alone gets "Normalizing the loudness of an audio source requires
the 'normalization' extra" with the extra installed.

```text
av 18.1.0, no numpy     15 of 30 normalization tests fail with that error
av 18.1.0 plus numpy    30 of 30 pass
```

CI installs no extras, so it cannot see this. The release builds install transcription
too, so they hide it.

### proposed fix

1. Add numpy to the `normalization` extra in `pyproject.toml`, and to
   `EXTRAS["normalization"].requirement`.
2. Run `python scripts/runtime/locks.py` and commit the changed locks. numpy moves into
   the normalization component, or into the base if transcription shares it.
3. Correct the comment at `normalizer.py:108`, and list numpy in the extras table in
   `docs/optional-extras.md`.

Done when a virtualenv with only `pip install -e ".[dev,normalization]"` passes
`tests/chronicler/core/processing/test_normalizer.py` and
`tests/chronicler/core/processing/handlers/test_normalizing.py`.

### related tickets

- (RELATED) [044-T4_extras_ci_job](044-T4_extras_ci_job.md): that job installs every lock together, which hides a component missing a dependency; see the note there
- (RELATED) [016-H1_server_component_for_binaries](016-H1_server_component_for_binaries.md): also regenerates the runtime locks
- (RELATED) [035-S11_regex_timeout_instead_of_guard](035-S11_regex_timeout_instead_of_guard.md): also regenerates the runtime locks
