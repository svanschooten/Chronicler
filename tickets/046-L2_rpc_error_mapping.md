# 046-L2_rpc_error_mapping

## Service errors reach thin clients as a bare 500

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: users lose the explanation. Change risk: low. |
| reach | Thin clients |
| effort | S |
| evidence | read in code |
| touches | `chronicler/core/rpc.py`, `chronicler/core/remote.py`, `tests/chronicler/server/test_rpc_routing.py` |

### description

The route wrapper (`rpc.py:108-122`) has no error mapping, so every service exception
becomes a generic 500. `RemoteServiceProxy` then raises `HTTPStatusError`. A local
explanation, such as the subtitle refusal or a rejected regex, never reaches a thin client
user.

### proposed fix

Map known exception types to status codes with a `detail`: `LookupError` to 404, and
`NoRealTimestampsError` and `UnsafePatternError` to 422. Have the proxy raise an error
carrying that detail, so `str(error)` reads the same as locally. Unknown errors stay a
generic 500, so paths do not leak.

Done when a refused SRT export on a thin client shows the same message as locally.

### related tickets

- (RELATED) [020-M3_explicit_timing_flag](020-M3_explicit_timing_flag.md): its refusal message is one of the cases
- (RELATED) [021-M10_reads_must_not_create_chronicles](021-M10_reads_must_not_create_chronicles.md): its `LookupError` is one of the cases
