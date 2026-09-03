# Audio normalisation

`chronicler/core/processing/normalizer.py`,
`chronicler/core/processing/handlers/normalizing.py`

Levels a track so a quiet participant and a loud one transcribe equally well. Whisper is
noticeably worse on under-gained audio, which is exactly what a Discord recording of six
people produces.

## Zero new dependencies

PyAV ships as a dependency of faster-whisper and exposes libavfilter, so `loudnorm`,
`speechnorm`, `afftdn`, `highpass` and `ebur128` are all already available. No librosa,
no soundfile, no ffmpeg binary on `PATH`.

## The source is never touched

Output goes to `<stem>.normalized.wav` **beside** the original. The original stays
exactly as recorded — it is the only irreplaceable artifact in the whole pipeline.

The `.normalized.wav` suffix is also how `list_audio_sources` knows to skip these when
listing tracks: they are derived files, not sources in their own right.

Output is always 16 kHz mono PCM, which is what Whisper wants anyway, so normalisation
doubles as the resample step.

## The filter chain

```text
highpass?  →  afftdn?  →  loudnorm  →  aresample(16k)  →  aformat(mono s16)
```

Optional stages come first on purpose: rumble and hiss should be gone *before* loudness is
measured, or the measurement is of the noise as much as the speech.

## LUFS in, dBFS out

`loudnorm` targets **LUFS** — perceptual loudness per EBU R128 — which is the right unit,
and why `target_lufs` is the setting rather than an RMS figure. The prototype's
`-20 dB RMS` target is not comparable across tracks with different dynamics.

The `loudness_before` / `loudness_after` figures recorded on the source are **RMS dBFS**,
not LUFS. That is a deliberate compromise: PyAV exposes no way to read filter metadata, so
the integrated loudness ffmpeg computes internally cannot be read back out. Rather than
report a number that is not measured, or hand-implement BS.1770 K-weighting, the recorded
figure is a real RMS measurement in a simpler unit.

It answers the question the panel actually asks — "was this track quiet, and is it still?"
— and it is comparable between tracks. Measured on a real under-gained tone:
**-39.5 → -17.1 dBFS**.

## Skipping work already done

Both the standalone task and the normalise-before-transcribe path go through
`ensure_normalized`, which returns `None` when a current normalized copy already exists.
"Current" means the source record says `DONE` **and** the recorded hash still matches the
file — so replacing a track re-offers the work. `force: true` on the task overrides it.

## Transcription prefers the normalized copy

`transcription_source` returns the normalized file when there is a current one and it
exists on disk, otherwise the original. This applies whether or not `normalize_first` was
requested: if a normalized copy is there, transcription uses it.

That is the point of tracking normalisation as state rather than inferring it from the
filesystem — the record says a normalized file *should* exist, and its absence is a
detectable inconsistency rather than a silent fallback to worse audio.

`normalize_first` failing is logged and does not fail the transcription. Worse audio is a
better outcome than no transcript.

## In the interface

The Sources panel shows a normalise action only when a track is not already normalized and
is not missing. A normalized track shows "Normalized" in its status line instead. There is
no greyed-out button for work that cannot be done.
