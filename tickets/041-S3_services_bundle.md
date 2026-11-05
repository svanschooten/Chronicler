# 041-S3_services_bundle

## Replace the DI container with an explicit Services object

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Medium: the container hides real constructor errors. Change risk: medium, touches every entry point and many tests. |
| reach | Internal. About 150 lines of app code and 160 of tests |
| effort | M |
| evidence | reproduced (swallowed constructor error) |
| touches | `chronicler/core/container.py`, `chronicler/core/local_container.py`, `chronicler/core/remote.py`, `chronicler/core/rpc.py`, `chronicler/core/handshake.py`, `chronicler/server/main.py`, `chronicler/desktop/runtime.py`, `chronicler/desktop/app.py`, `chronicler/desktop/main.py`, all desktop views, `scripts/thin_client_check.py`, `tests/chronicler/core/test_container.py`, `test_remote.py`, `test_rpc.py`, `test_file_staging.py`, `tests/chronicler/desktop/test_app.py`, `test_runtime.py`, `tests/chronicler/server/test_rpc_routing.py`, `docs/dependency-injection.md` |

### description

`container.py` and `local_container.py` are 154 lines of reflection to wire 4 services and
5 factories.

- A `T | None` parameter swallows real constructor errors. In a test, a dependency whose
  constructor raises `ValueError` resolved to `None`.
- `Settings | None` works only because resolving `Settings` raises `ValueError` on a
  pydantic parameter, which is then swallowed.
- `is_registered` and `cached` exist to work around its behaviour.
- It causes 3 `isinstance` branches in `desktop/app.py` and `Any`-typed resolvers.
- Views take optional arguments that only tests omit: `TranscriptView` has 12 parameters
  and `_no_stager`.

### proposed fix

```python
@dataclass
class Services:
    chronicles: ChronicleService
    tasks: TaskService
    transcripts: TranscriptService
    system: SystemService
    close: Callable[[], Awaitable[None]]

def local_services(db: DatabaseManager, settings: Settings) -> Services: ...
def remote_services(url: str, api_key: str, client: httpx.AsyncClient) -> Services: ...
```

`RpcServer` builds one per request, and `DesktopApp` one per view. A remote `Services`
holds proxies in the same fields, so views do not change behaviour. Views take `Services`,
and their optional arguments become required.

Schedule this on its own, because it conflicts with almost any open desktop PR.

Done when `container.py` is gone, there are no `isinstance` checks on the resolver, and
the thin-client check passes.

### related tickets

- (BLOCKER) [030-S2_remove_repository_abcs](030-S2_remove_repository_abcs.md): removes the factory registrations this replaces
- (BLOCKER) [023-S7_model_list_single_call](023-S7_model_list_single_call.md): changes `SystemService`
- (BLOCKER) [034-S8_simplify_handshake](034-S8_simplify_handshake.md): changes the handshake's use of the resolver
- (BLOCKER) [025-S9_single_mode_enum](025-S9_single_mode_enum.md): `build_runtime` is rewritten around the mode enum
- (BLOCKER) [019-M5_rpc_timeouts](019-M5_rpc_timeouts.md): introduces the shared client `remote_services` takes
- (BLOCKER) [027-M7_refresh_view_in_place](027-M7_refresh_view_in_place.md): both change how `DesktopApp` holds its views
- (BLOCKS) [043-S16_split_transcript_service](043-S16_split_transcript_service.md): new services go into the `Services` object
