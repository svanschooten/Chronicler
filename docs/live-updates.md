# Live updates for thin clients

`chronicler/core/task_events.py`, `chronicler/core/rpc.py`, `chronicler/core/remote.py`,
`chronicler/server/main.py`, `chronicler/desktop/app.py`

**Not built.** This is the agreed design for pushing task events to a thin client. It was
planned on 2026-08-13 and moved here from the old `TODO.md`.

## Where it stands

In full-stack mode the desktop and the `WorkerManager` share one event loop, so
`DesktopApp` subscribes to a `TaskEventBus` and refreshes the view on screen when a task
finishes (see [tasks.md](tasks.md#task-events)). A thin client has no such bus: RPC is
request and response only, and the server builds its `WorkerManager` without an
`event_bus`.

In the meantime the Tasks view polls while a task is running (ticket 064), which works on
a thin client without any push.

## Server-Sent Events, not WebSocket

Both were considered. SSE wins for this codebase:

- **The data only flows one way**, from server to client. Every client action already has
  a channel in the RPC routes, so a WebSocket's client-to-server half would go unused.
- **The thin client needs no new dependency.** It depends on `httpx`, which can read an
  SSE stream with `AsyncClient.stream()` and a few lines that parse `data: ...` blocks.
  A WebSocket client would need `websockets` or `httpx-ws` as a new base dependency:
  `websockets` is only present today through `uvicorn[standard]`, which is the `server`
  extra. The server needs nothing new either way, since a `StreamingResponse` with
  `media_type="text/event-stream"` is plain Starlette.
- **Reconnecting is hand-written either way** on the thin client, because httpx has no
  built-in client for either protocol.

## Server side

- `server/main.py` builds one `TaskEventBus` and passes it to both
  `build_worker_manager(..., event_bus=...)`, so the worker publishes, and `RpcServer`, so
  a route can subscribe.
- `RpcServer.build()` adds `GET /events` next to `/upload`. It is not a `@service`
  method: a stream does not fit the request and response shape of an exposed method. It
  sits behind the same API-key check as every other route.
- The handler creates an `asyncio.Queue`, subscribes a listener that calls
  `queue.put_nowait(event)`, and returns a `StreamingResponse` whose generator yields
  `data: <json>\n\n` for each event. It unsubscribes in a `finally` when the client
  disconnects; the return value of `TaskEventBus.subscribe()` is already the
  unsubscribe callable.
- `TaskCompletedEvent` is a frozen dataclass, so
  `TypeAdapter(TaskCompletedEvent).dump_python(event, mode="json")` serialises it, the
  same pattern `RemoteServiceProxy` uses for arguments.
- The worker and uvicorn already run on one event loop (`_serve_and_work` gathers both),
  so publishing from the worker and reading the queue in a request handler need no
  cross-thread signalling.

## Thin-client side

- A new class in `remote.py`, for example `RemoteTaskEventSource`, opens
  `client.stream("GET", f"{base_url}/events", headers={"X-API-Key": api_key})`, parses
  each event with `TypeAdapter(TaskCompletedEvent).validate_python(...)`, and publishes it
  into a local `TaskEventBus`. It runs as a background task and reconnects with backoff,
  so a server restart or a network blip does not stop updates for good.
- `DesktopApp` in thin-client mode builds its own `TaskEventBus`, subscribes
  `_on_task_completed` to it exactly as full-stack mode does, and starts the event source
  feeding it. The refresh code is then the same in both desktop modes; only where the
  events come from differs. That is why `TaskEventBus` was kept transport-agnostic.
