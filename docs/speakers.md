# Speakers

Speakers exist at two levels, deliberately.

## Per-chronicle speakers

`speakers` in each project database, referenced by transcript lines. These are the real
identities a transcript is attributed to, and they live with the Chronicle so it stays
portable.

`get_or_create_speaker` matches by exact name, so re-importing or re-cleaning reuses the
same row and therefore the same id.

## The workspace registry

`known_speakers` in the archive database records every name used anywhere in the
workspace, with a use count and last-used timestamp.

It exists for one reason: **the speaker picker should offer everyone you have ever
recorded, not just the people in this chronicle.** Without it, every new chronicle starts
with an empty dropdown and the same names get retyped — and a typo creates a near
duplicate that is invisible until an export looks wrong.

Names are matched case-insensitively and whitespace-normalised through
`normalized_name`, so `Alice`, `alice` and `  Alice  ` are one speaker. The first
spelling seen is the one kept and displayed.

`TranscriptService.speaker_suggestions` merges the registry with the chronicle's own
speakers and sorts case-insensitively — the registry is authoritative for breadth, the
chronicle for anything registered before the registry existed.

Registration is best-effort: if the registry write fails, the assignment still succeeds
and the failure is logged. A suggestion list is a convenience, and losing it should never
block attributing a track.

## Why not fan out across project databases

Answering "every speaker in this workspace" by opening every `project.db` is O(chronicles)
database connections per picker open. The registry is a denormalised index maintained on
write, which is the right trade for something read on every dialog.

## Linking brings its speakers with it

`ChronicleService.link_external_chronicle` runs `refresh_speaker_count`, which registers
every name it finds in the linked project database into the workspace-wide registry as
well as counting them. So a chronicle linked from elsewhere immediately contributes its
cast to every transcribe dialog's suggestions, which is the point of a workspace-wide
registry rather than a per-chronicle one.

The same call is what the chronicle view's *Identify speakers* action triggers, so
re-running it on any chronicle also tops up the registry.
