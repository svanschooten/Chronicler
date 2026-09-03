# Transcription parameters

`chronicler/core/processing/transcriber.py`,
`chronicler/core/processing/handlers/transcribing.py`

Nothing about transcription is hardcoded any more. Every value resolves through the same
three-level chain:

```text
explicit task payload  →  settings.transcription  →  the field's own default
```

| Parameter | Setting | Default |
| --------- | ------- | ------- |
| `language` | `transcription.language` | unset, meaning auto-detect |
| `no_speech_threshold` | `transcription.no_speech_threshold` | `0.6` |
| `model_size` | `transcription.model_size` | `base` |
| `device` | `transcription.device` | `cpu` |
| `compute_type` | `transcription.compute_type` | `int8` |

## Language

Previously `model.transcribe()` was called with no language at all, so Whisper
re-detected per file. On a short or noisy track that misfires, and because one track is
one speaker, a single mis-detection corrupts that participant's entire contribution.

`auto` is a real, selectable value rather than the absence of one. It matters because
absence means "fall back to the configured default" — so with a workspace configured for
Dutch, a task still needs a way to say *this* track is auto-detected. `auto` on the task
payload resolves to `None` at the model boundary.

`language_choices()` builds the picker's options: `auto` first, then the configured
`transcription.available_languages`, the UI locales, and the currently configured
language, deduplicated and sorted. The available list is itself a setting, so a language
that is not in the default set can be added without a code change.

## Model cache

Models are cached by `(model_size, device, compute_type)`, not by size alone. Switching
device or precision has to build a new model; keying on size alone would silently hand
back a CPU model after the user selected CUDA.

## What a run recorded

The effective language and model are written onto the source record
(`transcription_language`, `transcription_model`), so a track shows what it was actually
transcribed with rather than what the settings happen to say now.

The handler also marks the source `RUNNING` before starting and `FAILED` with the error
if it raises — so a failure is visible in the Sources panel, not only in the task list.

## The missing-extra guard

`faster-whisper` is imported lazily *inside* `_get_model`, so a missing `transcription`
extra only surfaces when a model is actually built. The `ImportError` guard therefore
wraps the **call**, not the import. It used to wrap an import that could never fail,
which meant the helpful "install the extra" message never actually appeared.

## Subtitles

`TranscriptService.export_srt` renders SubRip directly — the format is a counter, two
timestamps and a blank line, which is not worth a dependency.

It passes `require_real_timestamps=True`, which refuses a transcript whose timings are
synthetic line indices (`0→1`, `1→2`, `2→3` …) rather than real seconds. That is what the
text importer writes when a source carries no timings of its own, and subtitles built
from it would be silently meaningless. A single-line transcript is never judged
synthetic — there is no pattern to detect.

Cues with a zero or reversed duration are given a half-second minimum so players do not
skip them.
