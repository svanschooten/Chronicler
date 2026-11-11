# Security

Chronicler's server mode exposes every `@service` method over HTTP. Anything reachable
that way takes attacker-controlled input, including strings that end up as filesystem
paths or compiled regexes.

## Path confinement

`confine_to_directory` in `chronicler/core/file_staging.py` is the single
implementation of "this path came from an RPC caller, so it is not trustworthy". It
resolves the path and rejects anything landing outside the permitted root.

It is checked at the **point of access**, not at submission, so it covers every caller
regardless of how they obtained the string — not just ones that went through `/upload`.

| Call site | Confined to |
| --------- | ----------- |
| `ImportHandler.handle_import` | the workspace's `imports/` |
| `TranscribeHandler.handle_transcribe` | that chronicle's `sources/` |
| `ChronicleService.add_audio_source` | the workspace's `imports/` |

`HandlerBase.confine_to` delegates to it so handlers and services share one
implementation.

`add_audio_source` was the endpoint this was missed on. Both of its caller-supplied
strings feed a `shutil.move`. Unconfined, `file_path` would *move* any readable file on
the server into the chronicle — destroying the original and exposing its contents
through the transcript — and `original_name` was joined onto the sources directory
verbatim, so `"../../../../pwned.wav"` wrote outside the workspace entirely.

### Linked chronicles

`link_external_chronicle` takes a `project_path`, which is the "linked chronicle" feature
for local desktop use. It is the only way to place a chronicle's database outside the
workspace: it first checks that the file is a Chronicler project this version can open
(`check_linkable_project`). `create_chronicle` used to take a `project_path` too, without
that check, so a caller could have Chronicler's tables written into any SQLite file it
could name; it no longer does. Over RPC a `project_path` reaches further than it looks: adding a source creates `sources/` beside that path and moves an uploaded file into
it, cleaning creates `snapshots/` there, opening the chronicle runs the project migrations
against whatever SQLite file it names, and a zip export with sources reads everything in
that `sources/`.

So a server confines it. `LinkPolicy` refuses a path outside `server.linked_chronicle_dirs`
with `LinkRefusedError("not_allowed")`, before anything is read or created, and the list is
empty by default. The full-stack app registers no policy and links anywhere, since its
caller is the machine's own user. `update_chronicle` never changes `project_path`, so a
chronicle cannot be moved past the check afterwards.

## Filename sanitisation

Two different rules, for two different jobs.

**`sanitize_stage_name`** — for staged import files. Returns a fresh uuid4 with only a
whitelisted extension carried over. The original name never reaches the filesystem at
all, so a path-traversal or otherwise malicious filename cannot matter, regardless of
whether it came from an upload or a local file picker. The original is returned as
metadata, never used as a path.

**`safe_display_name`** — for a chronicle's audio sources, where the listing is meant to
show `session-3-gm.wav` rather than a uuid. Because the readable name is kept, it must
be reduced to a single harmless path component: directory separators in both POSIX and
Windows spellings, NT drive letters, ADS colons, and the `.` / `..` entries are all
stripped.

## Regex safety

User-supplied patterns (the custom import regex, cleaning strip patterns and regex
hallucination phrases) go through `chronicler/core/processing/regex_guard.py`.

Import regexes arrive from RPC callers and are matched against attacker-influenced
content, so a crafted pattern against a long line can make a backtracking engine run for
minutes. Two things bound that:

1. Patterns are compiled with the third-party `regex` package, capped at 500 characters.
   Every match goes through `run_timed`, which passes `timeout=` (5 seconds per call) and
   `concurrent=True`. A whole import or clean also shares one 60-second budget
   (`time_limit`), so a pattern just under the per-match limit cannot hold the worker for
   hours over a long transcript. Either timeout raises `PatternTimeoutError` and fails the
   task with a message naming the pattern.
2. `handle_import` and `handle_clean` run parsing and cleaning with `asyncio.to_thread`.
   `concurrent=True` releases the GIL while matching, so a slow pattern does not stall the
   window or other server clients. Moving the call to a thread alone would not help, since
   the standard `re` holds the GIL while it backtracks.

`TaskService.queue_import` and the settings models still compile the pattern at
submission time, so an overlong or invalid pattern is refused before a task exists.

## Authentication

An `X-API-Key` header, compared with `secrets.compare_digest`. `RpcServer` generates a
key if none is configured, so it is never accidentally unauthenticated.

The key is never logged. At startup the server logs only its last four characters, which
is enough to tell which key it expects. A server started with no key configured generates
one and saves it to the config file, because a key that existed only in the process
could not be handed to any client. Keys set through the environment are not copied
into the config file, and that file is owner-only on POSIX. See
[configuration.md](configuration.md#environment-values-are-not-saved).

There is no browser client and no CORS middleware. The web client this replaced was a
reverse proxy that answered every request with the server's key and asked for no login
of its own, so anyone who could reach it had the whole API.

## Transport

The server speaks plain HTTP and listens on every interface (`0.0.0.0`) unless `--host`
says otherwise. The API key therefore crosses the network unencrypted on every request,
and anyone who can see the traffic can read it and then use the whole API.

That is acceptable on a network you trust, such as a home LAN, and nowhere else. To
reach a server from anywhere less trusted:

* **Put it behind a TLS-terminating reverse proxy** (Caddy, nginx, Traefik) and bind the
  server itself to loopback with `--host 127.0.0.1`, so only the proxy reaches it. Point
  thin clients at the proxy's `https://` URL.
* **Or reach it over a tunnel**: an SSH port forward, WireGuard or Tailscale, again with
  the server bound to loopback or to the tunnel's address.

For a server only this machine uses, `--host 127.0.0.1` is enough on its own.

Chronicler has no TLS of its own, and the default stays `0.0.0.0` because a thin client
on another machine is the reason server mode exists.

## Uploads

`/upload` caps at `MAX_UPLOAD_SIZE` (500 MB, headroom for audio), and the cap holds while
the body is being received, not only once it has been.

Starlette spools a multipart body to a temporary file before the endpoint runs, so a check
in the endpoint alone limits what is kept, not what reaches the disk. FastAPI also reads
that body before it runs the endpoint's dependencies, the API key check among them, so
without more an unauthenticated client could make the server write up to the cap to disk
on every request. `_UploadGuard`, an ASGI middleware on `/upload`, closes both:

1. A missing `X-API-Key` gets a 401 and a wrong one a 403, the answers the app-wide check
   gives, before a byte of the body is read.
2. A declared `Content-Length` over the cap plus `MULTIPART_OVERHEAD` (64 KB for the
   boundary and part headers) gets a 413, also before anything is read.
3. It counts the bytes that actually arrive, so a client that sends no length, or a false
   one, is stopped with a 413 as soon as it passes the same limit.

The endpoint then holds the file itself to exactly `MAX_UPLOAD_SIZE` as it streams it in
1 MB chunks, and deletes a file that exceeds it rather than leave a partial.

## What is deliberately still open

* **No per-user identity.** One API key grants full access. Multi-user access control is
  not designed yet.
