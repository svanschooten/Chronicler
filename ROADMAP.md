# Roadmap

Where Chronicler goes next. What has landed is in [CHANGELOG.md](CHANGELOG.md).

**Concrete work is in [tickets/](tickets/README.md)**, which also gives the order to take
it in. As of 2026-11-20 one wave is open:

- **Wave 12, waiting on a decision:** retiring the PyInstaller build (059).

Everything below is direction without a ticket yet. When one is picked up, it gets a
ticket first.

## Transcripts and speakers

- Speaker diarization: several speakers recognised within one track. Today every source
  is one speaker's track.
- Audio playback synchronised with the transcript.
- Editing a line's timestamps.
- Resuming a transcription. A retry starts the track over.
- Cleanup markers, so a reader can see what a clean changed.

## Chronicles

- Tags of your own: add, remove and filter (ticket 066). Tags kept in `project.db` too,
  so a copied Chronicle keeps them.
- Title, description and kind travel with a zip export, but a `project.db` copied or
  linked on its own arrives without them.
- The create dialog does not yet assign speakers, metadata or tags.

## Processing

- Providers registered by annotation, with a `provider` field on `Task` recording which
  one ran.
- Concurrency configured per provider. The worker runs one task at a time.
- A general per-task CPU timeout. Only regex matching is bounded today.
- More AI tasks: analysis, action items, topic extraction, graph analysis.
- Semantic search and embeddings.

## Export

- Markdown and DOCX.

## Server and thin clients

- Push task events to thin clients over Server-Sent Events. The design is in
  [docs/live-updates.md](docs/live-updates.md). Until then the Tasks view polls.
- Storage management on the server.
- Switching the connection mode without restarting, and a new workspace folder that
  applies at once.

## Desktop

- Retry every failed task at once. Today it is one button per row.
- The window shows Flet's default icon, and the embedded-runtime build has none. The
  PyInstaller executable uses `assets/icon.png`.
- A deliberately chosen display font, registered through `page.fonts`, if one is wanted.
- The light theme was changed one fix at a time and has never been reviewed as a palette.

## Distribution and CI

- A macOS package, and the macOS CI entry back once `.venv` cache reuse is fixed.

## Later

- Multiple users, permissions, shared Chronicles and conflict handling.
- Additional client applications. If browser access comes back, Flet's web mode over the
  thin client is the first thing to try (see
  [docs/deployment-and-rpc.md](docs/deployment-and-rpc.md)).
