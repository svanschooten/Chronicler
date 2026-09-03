# Chronicler documentation

Chronicler's code carries no explanatory comments. Everything that would once have
been an inline comment — why a thing is built the way it is, what breaks if you change
it, which bug a line exists to prevent — lives here instead.

If you are about to write a comment explaining *why*, add it to the relevant page
below and leave the code clean.

## Pages

| Page | Covers |
| ---- | ------ |
| [configuration.md](configuration.md) | Settings, config file resolution, `--config`, the setup wizard |
| [configuration-sections.md](configuration-sections.md) | The nested `transcription` / `cleaning` / `normalization` / `llm` / `ui` groups |
| [dependency-injection.md](dependency-injection.md) | `Container`, scopes, why each unit of work gets its own session |
| [deployment-and-rpc.md](deployment-and-rpc.md) | The four modes, generated HTTP API, remote proxies, the web client |
| [storage.md](storage.md) | Archive and project databases, `DatabaseManager`, Alembic without an `alembic.ini` |
| [tasks.md](tasks.md) | Task lifecycle, atomic claiming, retries, the worker loop, task events |
| [processing.md](processing.md) | Import, clean and transcribe handlers; importers, cleaners, the transcriber |
| [cleaning.md](cleaning.md) | The cleaning rule pipeline, hallucination handling, measured results |
| [transcription.md](transcription.md) | Language, threshold and model resolution; SRT export |
| [speakers.md](speakers.md) | Per-chronicle speakers and the workspace-wide name registry |
| [audio-sources.md](audio-sources.md) | Per-track state: transcription, normalisation, speaker memory, fingerprints |
| [audio-normalization.md](audio-normalization.md) | The loudness pipeline, why the source is never touched, LUFS vs dBFS |
| [summarization.md](summarization.md) | LLM providers, model discovery, two-stage summarisation, numbered outputs |
| [recording.md](recording.md) | In-app capture, and why it needs no new RPC in thin-client mode |
| [i18n.md](i18n.md) | Message maps, `t()`, and the tests that keep translations honest |
| [security.md](security.md) | Path confinement, filename sanitisation, regex safety, API-key auth, upload limits |
| [desktop.md](desktop.md) | Flet views, theming, dialog patterns, the import coordinator |
| [testing.md](testing.md) | Test layout, shared fixtures, how views are tested |
| [troubleshooting.md](troubleshooting.md) | File dialogs, the session bus on WSL, and migration recovery |
| [thin-client-testing.md](thin-client-testing.md) | Handshake, the two-process check, and LAN exposure from WSL2 |

## Design notes

Longer-form proposals that are not yet built live in [design/](design/).

## Related documents in the repository root

* [README.md](../README.md) — what Chronicler is, and how to run it
* [ARCHITECTURE.md](../ARCHITECTURE.md) — the service architecture at a high level
* [HOWTO.md](../HOWTO.md) — practical operator guides
* [TODO.md](../TODO.md) — roadmap and current state of each feature
* [ASSESSMENT.md](../ASSESSMENT.md) — the Sprint-1-era audit, kept as a historical record
