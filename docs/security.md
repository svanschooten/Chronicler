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

`chronicler/core/processing/regex_guard.py` statically rejects patterns shaped for
catastrophic backtracking.

Import regexes arrive from RPC callers and are matched against attacker-influenced
content. `RegexImporter` matches line by line, so the realistic attack is a crafted
pattern against a long adversarial line, which can blow up matching time exponentially
in CPython's backtracking engine. Two shapes cause this in practice:

1. A quantified group whose own body is itself quantified — `(a+)+`.
2. A quantified group containing alternation whose branches can match overlapping
   content — `(a|a)*`, `(a|aa)+`. The engine can attribute the same matched text to
   different combinations of branch choices.

The guard walks the parsed pattern via `re._parser` looking for both, and caps pattern
length. `_leading_chars` returns `None` when it cannot determine a branch's leading
character set confidently, and callers treat that conservatively as "might overlap with
anything".

**It is not a CPU-time bound.** Python threads cannot be force-killed and CPython's
regex matcher does not release the GIL during backtracking, so a true hard bound needs
a subprocess watchdog. That is deliberately deferred — it overlaps with worker-loop work
already planned. The guard closes the realistic, textbook attack surface at zero runtime
cost.

The check runs in two places by design: `TaskService.queue_import` rejects at submission
time, and `RegexImporter.__init__` rejects again, because it can be constructed directly
by any other caller.

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
