# 028-P1_exports_off_event_loop

## PDF and zip exports freeze the app

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Medium: the UI freezes, and a server stops answering every client. Change risk: very low. |
| reach | All modes |
| effort | XS |
| evidence | measured |
| touches | `chronicler/core/services/transcript_service.py` |

### description

The desktop UI, or the HTTP server, shares one event loop with the worker. Two exports
block it:

```text
zip export, 200 MB audio     8,350 ms stall (8.4 s total)
PDF export, 1,686 turns      1,206 ms stall (1.27 s total, 4.9 s at 4x the size)
```

Every other operation measured stalled for 119 ms or less.

### proposed fix

Call `format_pdf` and `format_bundle` through `asyncio.to_thread` in `export_pdf` and
`export_zip`.

Done when a heartbeat coroutine stays under 100 ms during both exports.

### related tickets

- (BLOCKS) [037-P2_streamed_zip_export](037-P2_streamed_zip_export.md): builds on running the export off the event loop
- (RELATED) [037-P2_streamed_zip_export](037-P2_streamed_zip_export.md): that ticket then reduces the memory these exports use
- (RELATED) [045-T5_ruff_rules_and_target](045-T5_ruff_rules_and_target.md): covers the larger blocking calls Ruff cannot see
