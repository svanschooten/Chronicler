# 053-L9_upload_size_cap

## The upload cap does not limit what is received

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: an authenticated client can fill the temp disk. Change risk: low. |
| reach | Server |
| effort | S |
| evidence | read in code |
| touches | `chronicler/core/rpc.py`, `tests/chronicler/core/test_rpc.py`, `docs/security.md` |

### description

`/upload` checks the running total inside the handler (`rpc.py:169-195`), but Starlette
has already spooled the whole body to a temp file by then. So the 500 MB cap limits what
is kept, not what is received, despite `docs/security.md:87-89`.

The web proxy's in-memory buffering of uploads (`webclient/main.py:38`) goes away with the
web client.

### proposed fix

Reject on `Content-Length` before parsing, and count bytes in a small ASGI middleware on
that route for requests that lie about it.

Done when an oversized upload is rejected without writing the whole body to disk.

### related tickets

- (RELATED) [012-S14_remove_web_client](012-S14_remove_web_client.md): removes the proxy half of this problem
