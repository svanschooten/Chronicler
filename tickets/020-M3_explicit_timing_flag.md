# 020-M3_explicit_timing_flag

## The subtitle guard stops working after a clean or a line delete

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Medium: exports subtitles with meaningless timings. Change risk: low, adds a migration. |
| reach | Text-imported chronicles |
| effort | S |
| evidence | reproduced |
| touches | `chronicler/core/project_database.py`, `chronicler/core/models.py`, new migration in `chronicler/migrations/project/`, `chronicler/core/processing/importers.py`, `chronicler/core/formatting.py`, `chronicler/core/services/srt.py`, `chronicler/core/services/chronicle_service.py` |

### description

`looks_synthetic` (`formatting.py:71-81`) detects fake timings by their exact 0, 1, 2, 3
pattern, and `format_srt` relies on it (`srt.py:14`). A cleaned text import no longer has
that pattern, so the example transcript exports 1,242 subtitles starting at `00:00:00,000
--> 00:00:01,000`. Deleting one line has the same effect.

From the code, `hydrate_from_project` (`chronicle_service.py:83`) also derives a duration
from synthetic timings when linking a text-imported chronicle.

### proposed fix

Record whether timings are real when lines are created: a nullable `synthetic_timing`
column on `transcript_lines`, set by the importer and the transcriber, and preserved by
cleaning.

For older rows where it is `NULL`, keep a fallback: treat the transcript as synthetic if
every start and end time is a whole number.

Use the flag in `format_srt` and `hydrate_from_project`.

Done when a cleaned text import refuses SRT export, and a transcribed chronicle still
exports.

### related tickets

- (BLOCKER) [010-C5_transcript_line_source_id](010-C5_transcript_line_source_id.md): both add a project migration on the same table, so this one rebases on it
- (BLOCKS) [063-F1_full_text_search](063-F1_full_text_search.md): same migration chain, so this rebases on it
- (RELATED) [046-L2_rpc_error_mapping](046-L2_rpc_error_mapping.md): the refusal message must also reach thin clients
- (RELATED) [010-C5_transcript_line_source_id](010-C5_transcript_line_source_id.md): both add a project migration on the same table, so this one goes first
