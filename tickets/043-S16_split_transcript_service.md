# 043-S16_split_transcript_service

## Split TranscriptService

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: maintenance cost only. Change risk: medium, moves RPC routes. |
| reach | Internal. No net change in lines |
| effort | M |
| evidence | read in code |
| touches | `chronicler/core/services/`, `chronicler/core/rpc.py`, `chronicler/server/main.py`, `chronicler/desktop/`, `tests/chronicler/core/services/`, `tests/chronicler/core/test_rpc.py`, `docs/deployment-and-rpc.md` |

### description

`TranscriptService` is 339 lines and holds 16 of the 36 RPC methods: reading, editing,
exports, audio sources, summaries and speakers. `html.py`, `pdf.py`, `srt.py` and
`bundle.py` are formatters living in `services/`. `read_transcript_text` is an alias of
`export_plaintext`, and both are exposed.

Prototype traces remain: `getattr(line, "timestamp", None)` and `float(str(ts))`
(`pdf.py:21-22`, `html.py:25-26`), and a `GM` speaker style in the general HTML export
(`html.py:24`).

### proposed fix

Split out exports, sources and summaries as services, and move the formatters to
`core/exports/`. Remove the alias and the prototype traces. Client and server must match
versions exactly, so moved routes cannot break a compatible pair.

Done when each service has one topic, and the thin-client check passes.

### related tickets

- (BLOCKER) [041-S3_services_bundle](041-S3_services_bundle.md): new services go into the `Services` object
- (BLOCKER) [032-S4_project_db_access](032-S4_project_db_access.md): uses the project database helper
- (BLOCKER) [037-P2_streamed_zip_export](037-P2_streamed_zip_export.md): changes the export methods
- (RELATED) [048-L4_audio_file_filter](048-L4_audio_file_filter.md): edits `_on_disk`, which moves here
