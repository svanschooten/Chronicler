# 037-P2_streamed_zip_export

## Zip exports hold everything in memory

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Medium: high memory use on both ends, and audio archives are impractical over HTTP. Change risk: medium, extends the RPC layer. |
| reach | Zip export in all modes, mostly thin clients |
| effort | M |
| evidence | measured time; memory read in code |
| touches | `chronicler/core/services/bundle.py`, `chronicler/core/services/transcript_service.py`, `chronicler/core/rpc.py`, `chronicler/core/remote.py`, `chronicler/desktop/views/transcript/export.py`, `docs/deployment-and-rpc.md`, `docs/storage.md` |

### description

`format_bundle` (`bundle.py:68-78`) builds the archive in a `BytesIO`, then copies it to a
`bytearray`, and the RPC layer holds it again on both ends. Encoded audio also goes
through DEFLATE, which takes time and gains almost nothing.

### proposed fix

1. Build the zip in a temp file, and store audio with `ZIP_STORED`.
2. Have `export_zip` return a `Path`. `RpcServer` sends it with `FileResponse` and deletes
   it afterwards, and `RemoteServiceProxy` streams it to a local temp file.
3. `TranscriptExporter._save` moves the file instead of writing bytes.

Done when a 200 MB export does not grow process memory by 200 MB, and works on a thin
client.

### related tickets

- (BLOCKER) [028-P1_exports_off_event_loop](028-P1_exports_off_event_loop.md): builds on running the export off the event loop
- (BLOCKS) [043-S16_split_transcript_service](043-S16_split_transcript_service.md): changes the export methods
- (RELATED) [019-M5_rpc_timeouts](019-M5_rpc_timeouts.md): shorter read timeouts become possible once this streams
- (RELATED) [028-P1_exports_off_event_loop](028-P1_exports_off_event_loop.md): that ticket then reduces the memory these exports use
