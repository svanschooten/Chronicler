# 048-L4_audio_file_filter

## Any file in sources/ counts as an audio track

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: stray rows such as `desktop.ini`. Change risk: very low. |
| reach | All modes |
| effort | XS |
| evidence | read in code |
| touches | `chronicler/core/services/transcript_service.py`, `chronicler/desktop/operations.py` |

### description

`_on_disk` (`transcript_service.py:174-179`) only excludes normalized copies, so
`desktop.ini` or `.DS_Store` appear as tracks that can be transcribed. Copying tracks in
by hand is a supported workflow, so the folder cannot be assumed clean.

### proposed fix

Move `AUDIO_EXTENSIONS` from `desktop/operations.py:27` into core, extend it with common
formats such as `opus`, `webm` and `aac`, and filter `_on_disk` by it and by hidden files.

Done when a `desktop.ini` in `sources/` is not listed.

### related tickets

- (RELATED) [043-S16_split_transcript_service](043-S16_split_transcript_service.md): edits `_on_disk`, which moves here
