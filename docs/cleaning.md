# Transcript cleaning

`chronicler/core/processing/cleaners.py`, configured by `CleaningSettings`

Raw speech-to-text output is not usable as-is. Whisper invents phrases during silence,
loops on breath and room tone, and emits the same segment twice at overlapping
timestamps. Cleaning is an ordered pipeline of single-purpose rules that each fix one
of those.

Every rule is individually switchable and parameterised, and the defaults work with no
configuration at all.

## The pipeline

Order is fixed and matters — normalisation has to happen before matching, and merging
has to happen last so it merges only lines that survived.

| # | Rule | Setting | What it fixes |
| - | ---- | ------- | ------------- |
| 1 | `CollapseWhitespace` | `collapse_whitespace` | Ragged spacing and embedded newlines from importers |
| 2 | `StripPatterns` | `strip_patterns` | Source-specific junk, e.g. `[laughs]` annotations |
| 3 | `DropEmpty` | always on | Lines the two rules above emptied |
| 4 | `DropHallucinations` | `drop_hallucinations`, `hallucination_phrases`, `hallucination_match` | Phrases the model invents over silence |
| 5 | `DropShortLines` | `min_characters` | Fragments too short to carry meaning |
| 6 | `DropDuplicateSegments` | `drop_duplicate_segments` | The same segment emitted twice at the same time |
| 7 | `DropRepeats` | `drop_repeats`, `repetition_window_seconds` | The model looping on silence |
| 8 | `MergeSameSpeaker` | `merge_same_speaker` | One speaker's consecutive turns split across segments |

Rules 3 and 5 always run; setting `min_characters` to `0` makes rule 5 a passthrough.

## Hallucination matching

`hallucination_match` picks how `hallucination_phrases` are compared:

* **`normalized`** (default) — casefold, then strip surrounding punctuation and
  whitespace. `"You."`, `"you"` and `"YOU!"` all match the phrase `you`.
* **`exact`** — literal string equality. Use when you need to drop one precise spelling
  and nothing near it.
* **`regex`** — each phrase is a pattern, matched case-insensitively with `fullmatch`
  against the stripped line. `Full`match, not `search`, so `Ondertiteling door.*` drops
  a line that *is* that phrase rather than any line containing it.

Regex phrases and `strip_patterns` both go through
[the ReDoS guard](security.md#regex-safety) at configuration-validation time, so a
catastrophic pattern is rejected when it is set rather than when a task runs.

## Why the defaults are conservative

`DEFAULT_HALLUCINATION_PHRASES` deliberately excludes `"Okay."`, `"Thank you."` and
`"Bye."`, even though Whisper does hallucinate all three.

They are also ordinary speech. Silently deleting a real "Okay." loses dialogue, and a
transcript that quietly drops real lines is worse than one that keeps an invented one —
you can see and delete an invention, but you cannot see an omission.

The repeat rule covers the loop case anyway, which is what makes this affordable. See
the measurement below.

## Changing the language

The phrase list is replaced wholesale, not appended to, so switching languages is one
setting:

```yaml
cleaning:
  hallucination_phrases:
    - "Ondertiteling door"
    - "Ondertiteld door de Amara.org gemeenschap"
```

## Per-task overrides

A `CLEAN` task payload may carry a `cleaning` key holding any subset of
`CleaningSettings`. It replaces the workspace default for that run only, so a one-off
aggressive clean does not mean editing configuration:

```json
{"cleaning": {"min_characters": 3, "repetition_window_seconds": 60}}
```

An invalid override fails the task with a clear message rather than silently falling
back to defaults.

## Measured against real data

Run over `50.transcript.txt`, a genuine 2,816-turn D&D session from the v0 prototype:

| Stage | Turns |
| ----- | ----- |
| Parsed | 2,816 |
| Whitespace and merge only (the old behaviour) | 2,814 |
| Full default pipeline | 2,166 |

**650 turns — 23% — were junk.** The breakdown is the argument for the design:

* 16 removed as hallucinations, almost all bare punctuation (`...`, `.`)
* 401 removed as repeat loops, led by **232 occurrences of `"Thank you."`**

That 232 is the point. `"Thank you."` is not in the default phrase list, and it does not
need to be: the repeat rule catches the loop while leaving a genuine, isolated
"Thank you." in place. Precision and recall at the same time.

The `you` artifact does not appear in that measurement because the prototype's own SQL
export already filtered it before writing the file — see
[the prototype salvage notes](design/prototype-salvage.md).
