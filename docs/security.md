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
   `concurrent=True`. A timeout raises `PatternTimeoutError` and fails the task with a
   message naming the pattern.
2. `handle_import` and `handle_clean` run parsing and cleaning with `asyncio.to_thread`.
   `concurrent=True` releases the GIL while matching, so a slow pattern does not stall the
   window or other server clients. Moving the call to a thread alone would not help, since
   the standard `re` holds the GIL while it backtracks.

`TaskService.queue_import` and the settings models still compile the pattern at
submission time, so an overlong or invalid pattern is refused before a task exists.

## Authentication

An `X-API-Key` header, compared with `secrets.compare_digest`. `RpcServer` generates a
key if none is configured, so it is never accidentally unauthenticated.

The web client never hands the browser the upstream key. `/config` returns only
`{"connected": bool}`, and the `/api/...` proxy routes inject the header server-side.

## Uploads

`/upload` caps at `MAX_UPLOAD_SIZE` (500 MB, headroom for audio) and streams in 1 MB
chunks, checking the running total as it goes rather than trusting a declared
`Content-Length`. A file that exceeds the cap is deleted rather than left as a partial.

## What is deliberately still open

* **`create_chronicle(project_path=...)`** lets a caller name a path outside the
  workspace. That is the intentional "linked chronicle" feature for local desktop use;
  it is worth revisiting for hardened server deployments.
* **No per-user identity.** One API key grants full access. Multi-user access control is
  not designed yet.
