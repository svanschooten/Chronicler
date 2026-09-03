# Deployment modes and RPC

`chronicler/core/rpc.py`, `chronicler/core/remote.py`, `chronicler/webclient/main.py`,
`chronicler/server/main.py`

The same application services do the work in every deployment mode. What changes is how
a client reaches them.

## Modes

| Mode | UI | Services | Storage |
| ---- | -- | -------- | ------- |
| Full stack | Local Flet | In process | Local workspace |
| Server | None | In process | Local workspace |
| Thin client | Local Flet | Remote, over HTTP | On the server |
| Web client | Browser | Remote, proxied | On the server |

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

## CORS

`allow_credentials=False` with a wildcard origin is deliberate. Auth here is a
bearer-style `X-API-Key` header, not a cookie, so browsers never attach it
automatically the way they do credentials. `allow_credentials=True` combined with a
wildcard origin would be both invalid — browsers reject the combination — and
unnecessary.

## The web client proxy

The browser never receives the upstream API key. `/config` reports only
`{"connected": bool}`; the `/api/...` routes inject `X-API-Key` server-side when
forwarding. An upstream failure becomes a 502 rather than a stack trace.

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
