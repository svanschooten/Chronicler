# Deployment modes and RPC

`chronicler/core/rpc.py`, `chronicler/core/remote.py`, `chronicler/server/main.py`

The same application services do the work in every deployment mode. What changes is how
a client reaches them.

## Modes

| Mode | UI | Services | Storage |
| ---- | -- | -------- | ------- |
| Full stack | Local Flet | In process | Local workspace |
| Server | None | In process | Local workspace |
| Thin client | Local Flet | Remote, over HTTP | On the server |

There was a fourth, a browser client behind a reverse proxy. It was removed: it exposed
the full API with no login of its own, for three operations. If browser access is wanted
again, Flet's web mode over the thin client is the first thing to try. The code is in git
history.

A config still saved with `mode: client:web` reads as if no mode were set, with a warning.
The desktop then infers thin client from its server URL instead of failing to start. See
[configuration.md](configuration.md#settingsmode).

## The generated API

`RpcServer` turns every `@service`-decorated class into a set of `POST` routes.
`ChronicleService.list_chronicles` becomes `POST /chronicle/list_chronicles`; the
`Service` suffix is stripped and the rest lowercased.

Only coroutine functions are exposed. That is why `TranscriptService.list_audio_sources`
is `async` despite being plain filesystem I/O.

Every parameter becomes a body field. The method's own default is preserved, including
`None`. An earlier version used `Body(...)` unconditionally, which made every parameter
mandatory regardless of the actual signature, so any caller that omitted or explicitly
passed `None` for a genuinely optional argument got a 422.

Each request gets a fresh `Container` scope — see
[dependency-injection.md](dependency-injection.md).

## Documents come back as bytes, not JSON

A method annotated `-> bytes` or `-> bytearray` is served as
`application/octet-stream` instead of being run through a response model, and
`RemoteServiceProxy` reads `response.content` for it rather than `response.json()`.

This is what makes the document exports work remotely. JSON cannot carry bytes, so
`export_pdf` and `export_zip` had no way over the wire at all, and because an unexposed
method is never installed on the proxy, a thin client's Export menu raised
`AttributeError` rather than failing gracefully — HTML was in the same position for no
reason beyond being listed next to them. Base64 in a JSON field would have worked too,
at a third more bytes and a decode on each end.

The whole document is held in memory on both sides, which is the reason a Chronicle
archive leaves the audio out unless it is asked for — see
[storage.md](storage.md).

Without a container there is nothing to resolve service instances from, so only
`/upload` (which needs just a `DatabaseManager`) is registered in that case.

## Remote proxies

`RemoteServiceProxy` mirrors a service class over HTTP. It inspects the class, and for
each public coroutine method installs a callable that serialises the arguments, posts
them, and validates the response back into the declared return type.

Arguments are serialised **per their declared parameter type** via `TypeAdapter`, not
by inspecting the runtime value. That handles `UUID`, `datetime`, `Path`, enums and
Pydantic models uniformly. The previous `hasattr(v, "model_dump")` check only handled
Pydantic models, so a bare `UUID` chronicle id — the single most common argument shape
in this codebase — fell through unserialised and failed httpx's JSON encoding outright.

`RemoteContainer` resolves the same service classes to proxies, so a view cannot tell
whether it is talking to a local instance or a remote one.

## Refusals keep their message

A service refuses some things in words meant for the user: an unknown chronicle, a transcript
with no real timestamps for subtitles, a rejected regex. `rpc.refusals()` lists those
classes. The route wrapper sends one as a 404 (`LookupError`) or 422, with
`{"detail": {"error": "<class name>", "message": "..."}}`, and `RemoteServiceProxy` raises
the same exception class with the same message, so `str(error)` and an `except` clause read
as they do against a local service.

Everything else is a bug or may hold something private, such as a path in a locked-database
error, and stays a bare 500. `KeyError` and `IndexError` are `LookupError`s but are left out
for the same reason: their text is just a key. To explain a new error, add its class to
`refusals()`; it must be constructible from its message alone.

## No CORS

The API installs no CORS middleware, so browsers refuse cross-origin calls to it. Every
client is a Flet app or a script, none of which needs an allowed origin.

## Server mode runs a worker too

`uvicorn.run()` is synchronous and owns its own event loop, so running a worker loop
alongside it means driving `uvicorn.Server.serve()` directly on the same loop as the
worker. A second OS thread would need its own `DatabaseManager` and engine, because
aiosqlite connections are bound to the event loop that created them.

Before this, tasks queued against a server were never executed at all — `run_server()`
never created a `WorkerManager`.

## Capabilities: the server answers, the client asks

`ServerInfo.capabilities` is how a client finds out what the service layer can actually
do. `capabilities_for(settings)` builds it from two things the client cannot see:

* which optional extras import on that machine — `transcribe`, `normalize`
* whether a language model is configured there — `summarize`

`import`, `clean` and `export` need nothing and are always present.

A thin client must not decide this for itself. The worker that would run a transcribe or
summarize task is on the server, so the server's extras and the server's model
configuration are the ones that matter; a client with `faster-whisper` installed and a
server without it would offer a button that always fails.

`DesktopApp.refresh_models` fetches the capabilities once at startup, alongside the model
list, because both are a round trip and neither changes while the app runs. A failed
fetch leaves `capabilities` as `None`, which every consumer reads as "assume it works"
rather than greying out actions over a network hiccup.

Recording is deliberately absent from the list. It runs client-side in every mode, so a
server capability would be answering the wrong question — see [recording.md](recording.md).

## Exposure is explicit

`@service(expose=[...])` names the methods that become HTTP routes. Anything not named is
not published, however public or async it is.

It used to be implicit: `@service` published every public coroutine. That made the API
contract a side effect of an implementation detail — a helper that gained an `await`
became a route, without anyone deciding it should. Two did exactly that, and served the
server's absolute filesystem paths to any authenticated client:

```text
POST /transcript/source_path  {"filename": "../../../../etc/passwd"}
  -> 200  "/ws/chronicles/<id>/sources/../../../../etc/passwd"
```

Nothing read the file, so this was path disclosure rather than traversal — but the
mechanism would have kept producing endpoints nobody chose. The audit that found it also
found that 15 of the 45 published methods were unreachable from any client.

The list is validated when the class is decorated: naming a method that does not exist,
or one that is not a coroutine, fails at import time rather than 404ing at runtime.
`RemoteServiceProxy` builds its methods from the same list, so a thin client fails
locally and clearly instead of over the wire.

`tests/chronicler/core/test_rpc.py` asserts the exact size of each service's surface, so
growing the API is a deliberate edit to a number rather than a side effect of writing a
method.
