# 019-M5_rpc_timeouts

## Every thin-client call has a 5-second timeout

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Medium: long exports always fail on a thin client. Change risk: low. |
| reach | Thin clients |
| effort | XS |
| evidence | timeout value confirmed; failures inferred from measured durations |
| touches | `chronicler/core/remote.py`, `chronicler/core/file_staging.py`, `chronicler/desktop/runtime.py`, `chronicler/desktop/app.py` |

### description

`remote.py:23` and `file_staging.py:84` use a bare `httpx.AsyncClient()`, which defaults
to `Timeout(5.0)`. The server builds a zip before sending its first byte. A chronicle with
200 MB of audio took 8.4 s in the audit, so that export should always time out. A
transcript four times the example's size spends about 5 s in PDF rendering alone.

Each proxy also creates its own client, and none is ever closed.

### proposed fix

Create one `httpx.AsyncClient(timeout=httpx.Timeout(10, read=600, write=600))` in
`build_runtime`, share it between `RemoteContainer` and `RemoteFileStager`, and close it
in `DesktopApp.cleanup`.

Done when a test confirms the configured timeouts on both, and there is one client per
process.

### related tickets

- (BLOCKS) [041-S3_services_bundle](041-S3_services_bundle.md): introduces the shared client `remote_services` takes
- (RELATED) [037-P2_streamed_zip_export](037-P2_streamed_zip_export.md): streaming exports reduces how long the read timeout must be
