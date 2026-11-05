# 018-M2_unicode_speaker_names

## The default importer folds non-ASCII speakers into the previous turn

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Medium: text is attributed to the wrong person, with no warning. Change risk: very low. |
| reach | Any text import with non-ASCII speaker names. The UI ships in German and Dutch |
| effort | XS |
| evidence | reproduced |
| touches | `chronicler/core/processing/importers.py`, `HOWTO.md`, `tests/chronicler/core/processing/test_importers.py` |

### description

`DefaultImporter` uses `^([A-Za-z0-9 _]+)\s*:(.*)$` (`importers.py:99`). A line that does
not match continues the turn above it.

```text
input    Anna: hallo / Jürgen: guten Tag / José: hola / Anna: tot ziens
result   Anna: "hallo\nJürgen: guten Tag\nJosé: hola"
         Anna: "tot ziens"
```

### proposed fix

Use `^([\w .'-]+?)\s*:(.*)$`. This was checked during the audit: `assert_safe_pattern`
accepts it, the sample above parses into four correct turns, and
`examples/example_transcript_001.txt` parses identically to today (1,686 turns).

Also log how many lines were dropped before the first speaker, which is the one case where
text disappears, and update `HOWTO.md:134`.

### related tickets

- none
