# 034-S8_simplify_handshake

## Reduce the handshake to one function

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: maintenance cost only. Change risk: low. |
| reach | Internal, thin-client startup. About 40 lines |
| effort | XS |
| evidence | read in code |
| touches | `chronicler/core/handshake.py`, `chronicler/core/services/system_service.py`, `scripts/thin_client_check.py`, `tests/chronicler/core/test_handshake.py`, `tests/chronicler/server/test_rpc_routing.py` |

### description

`handshake.py` is 73 lines with 3 exception classes and a result dataclass. The one
production caller ignores the result (`desktop/main.py:100`),
`require_matching_version=False` is only used in tests, and it loads every chronicle twice
to log a count: once in `get_server_info` and once in `list_chronicles`.

### proposed fix

One `perform_handshake(resolver) -> ServerInfo` that raises `HandshakeError` with a clear
message. Count chronicles with `SELECT count(*)`, or drop the field if only the log uses
it. Adapt `scripts/thin_client_check.py`.

Done when the thin-client check still passes.

### related tickets

- (BLOCKS) [041-S3_services_bundle](041-S3_services_bundle.md): changes the handshake's use of the resolver
