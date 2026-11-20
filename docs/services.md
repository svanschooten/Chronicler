# Services

`chronicler/core/services/services.py`

The four services — chronicles, tasks, transcripts and system — are built together, as one
`Services` object, for one unit of work:

```python
@dataclass
class Services:
    chronicles: ChronicleService
    tasks: TaskService
    transcripts: TranscriptService
    system: SystemService
    close: Callable[[], Awaitable[None]]
```

Two functions make one, and nothing else wires services:

| Function | Builds | `close` |
| -------- | ------ | ------- |
| `local_services(db_manager, settings, link_policy=None)` | The real services over a workspace, on one new archive session | Returns that session to the pool |
| `remote_services(url, api_key, client)` | A `RemoteServiceProxy` in each field, over one shared `httpx.AsyncClient` | Does nothing: a proxy holds nothing open |

Because a remote `Services` has the same fields, a view does not know which it has.

An earlier version resolved these through a reflection-based container that read
constructor type hints. A `T | None` parameter swallowed a real constructor error, and it
needed `is_registered` and `cached` to work around its own behaviour. Building the four
services by hand is about 20 lines and a wrong argument is a type error.

## One unit of work, one session

Every repository in a local `Services` shares its one `AsyncSession`, so a unit of work gets
its own `Services` and closes it when done. Anything shared across units of work would
share a session, which is not safe under concurrent use, and a session nobody closes holds
a read transaction open (see [troubleshooting.md](troubleshooting.md)).

Units of work are:

* **A request.** `RpcServer` is given a `new_services` function, builds a set for each call
  and closes it in a `finally`.
* **A view.** `DesktopApp._new_services` makes one for the view about to be shown, and
  closes it when navigating away or on cleanup.
* **A one-off.** `DesktopApp.refresh_models` and the startup handshake make a set, ask,
  and close it.

`DesktopRuntime.new_services` is the function that makes one in either mode, built once
from `Settings` in `build_runtime`.

## Serving

`RpcServer(new_services, db_manager, services=[...])` publishes only the classes in
`services`, and finds each in a request's set with `Services.of(cls)`. The `db_manager` is
for `/upload`, which writes into the workspace's imports folder.

`build_rpc_server` in `server/main.py` is where the server's one `LinkPolicy` (the folders
a remote caller may link from) is given to `local_services`.
