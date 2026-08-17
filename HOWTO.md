# Chronicler How-To Guides

This document provides practical guides for configuring and running Chronicler in various modes.

## Setting Up Chronicler

When you run Chronicler for the first time without a configuration file, the configuration wizard will start automatically.

```bash
python -m chronicler
```

The wizard will ask you how you would like to run Chronicler.

### Running as Full Stack (Local)

1. Select option **1. Full Stack**.
2. Enter the path where you want to store your workspace (default: `~/ChroniclerWorkspace`).
3. Choose to generate or enter an API key. If you choose to enter one but leave it blank, a new key will be automatically generated for you.
4. Start the application: `python -m chronicler`.

### Running as a Server

1. Select option **3. Server**.
2. Enter the workspace path.
3. Generate or enter an API key. This key will be required by any Thin Clients or Web Clients connecting to this server.
4. Start the server: `python -m chronicler server`.

### Running as a Thin Client

1. Ensure you have a Chronicler Server running and you have its URL and API key.
2. Select option **2. Thin Client**.
3. Enter the Server URL (e.g., `http://192.168.1.10:8000`).
4. Enter the API key provided by the server (if you leave this blank, a new key will be generated, but it must match the server's key to work).
5. Start the application: `python -m chronicler`.

### Running the Web Client (Server)

1. Ensure you have a Chronicler Server running.
2. Select option **4. Web Client (Server)**.
3. Enter the Server URL and API key.
4. Start the web client server: `python -m chronicler web`.
5. Open your browser at `http://localhost:8080`.

The Web Client allows you to:
- Browse your Chronicles.
- Create new Chronicles.
- Upload audio files or transcripts directly to the server for processing.

---

## Configuration File Locations

Chronicler looks for configuration in the following locations:

1. `~/.chronicler_config.yaml` (Recommended)
2. OS-specific configuration directory (e.g., `~/.config/Chronicler/settings.yaml` on Linux).

You can manually edit these files to change your settings.

### Using a specific config file

To bypass that search entirely:

```bash
python -m chronicler --config /path/to/custom.yaml
```

`CHRONICLER_CONFIG_FILE=/path/to/custom.yaml` does the same thing, and is inherited by
subprocesses. Settings changed in the app are saved back to that file, and the wizard
writes there too — so `--config` gives you a fully self-contained instance.

Use it to keep more than one workspace on a machine (a work archive and a D&D archive, say)
without either one's settings overwriting the other's, or to run a throwaway instance
against a scratch workspace.

A config file named with `--config` that doesn't exist yet is treated as "no configuration"
rather than falling back to your normal one, so the wizard will run and create it. That is
deliberate: silently loading your real config would defeat the point of asking for a
specific file.

Individual settings can also be overridden by environment variables using the
`CHRONICLER_` prefix — `CHRONICLER_WORKSPACE_PATH`, `CHRONICLER_API_KEY` and so on. These
take precedence over the config file.

### Example `settings.yaml`

```yaml
workspace_path: /home/user/ChroniclerWorkspace
api_key: some-secret-key
server_url: null
app_name: Chronicler
mode: desktop:full_stack
dark_mode: true
```

`mode` is one of `desktop:full_stack`, `desktop:thin_client`, `server` or `client:web`,
and is written by the wizard. A config saved before `mode` existed still works — the
mode is inferred from whether a workspace path or a server URL is present.

Chronicler validates the configuration against the mode it is starting in, and re-runs
only the wizard steps needed to fill in what's missing. So if you hand-edit this file
into an inconsistent state, the wizard will ask about the specific gap rather than
starting over.

---

## Enabling Optional Features

Two features need extra dependencies, so a default install stays small:

```bash
pip install -e ".[server]"
```

Needed to run `python -m chronicler server` or `python -m chronicler web` (FastAPI,
Uvicorn, multipart upload support).

```bash
pip install -e ".[transcription]"
```

Needed for `TRANSCRIBE` tasks (faster-whisper). Without it, a queued transcription fails
with an explanatory error rather than crashing. The model itself is downloaded on the
first real transcription, not at startup — so expect the first one to take noticeably
longer than later ones.

---

## Importing a Transcript With a Custom Format

The transcript importer is regex-driven, so most exported formats can be read without
pre-processing. In the Import Transcript dialog:

* **Line Regex** — must match one transcript line, with capture groups for the parts you
  want. The default (`^([A-Za-z0-9 _]+)\s*:(.*)$`) handles `Alice: hello`.
* **Speaker Group Index** / **Text Group Index** — which capture groups hold the speaker
  and the text.
* **Timestamp Group Index** — optional. Set it if your format carries a timestamp, e.g.
  group `1` for `^\[(\d\d:\d\d:\d\d)\] ([A-Za-z]+):\s*(.*)$` with speaker `2` and text
  `3`. Leave it blank and lines get sequential synthetic positions instead, which is why
  a text-imported Chronicle shows no duration.

Timestamps are accepted as `HH:MM:SS`, `MM:SS`, and with a fractional-seconds suffix.

Patterns are checked for catastrophic-backtracking shapes before a task is created, so a
pattern like `(a+)+$` is rejected up front rather than hanging a worker. Note this is a
static shape check, not a CPU-time limit.

### Importing a second transcript

Importing into a Chronicle that already has a transcript asks whether to **overwrite** or
**append**. Appending shifts the new file's line positions past the existing ones, so
ordering is preserved.

---

## Transcribing Audio

Importing audio and transcribing it are separate steps.

1. **Import Audio** (header menu, or a Chronicle card's import menu) stores the file in
   that Chronicle's `sources/` directory under its original name. Nothing is transcribed
   yet.
2. Open the Chronicle and use the **Sources** panel in the right-hand column. Each track
   has a transcribe button, which asks which speaker the track belongs to.

One audio source is treated as one speaker's track — there is no diarization yet.
Transcribing a track replaces only that speaker's existing lines, so other speakers'
already-transcribed tracks survive. Existing speaker names are offered as a hint; typing
one exactly reuses that speaker instead of creating a near-duplicate.

Because each track is assumed to be time-aligned with the others (as separate tracks from
one recording session are), segment timestamps are used as-is and the combined transcript
interleaves speakers correctly when sorted.

---

## Sharing or Relocating a Chronicle

Every Chronicle is a self-contained directory, so moving one is a filesystem operation:

* **Copy or archive** `chronicles/<chronicle-id>/` and it takes its transcript, speakers
  and audio sources with it. It will be migrated to the current schema the first time it
  is opened.
* **Link an existing Chronicle** with **Import → Link External Chronicle** and pick its
  `project.db`. Chronicler records the path rather than copying the file, and the
  Chronicle is titled after its containing directory.

A linked Chronicle's data stays where you put it — deleting it from Chronicler removes
the workspace's record of it and never touches the external file. Deleting a normal
Chronicle *does* remove its directory.

---

## Backing Up

There is nothing Chronicler-specific to do: copy the workspace directory. It contains
`chronicler.db` (the Chronicle index, task queue and tags) plus one directory per
Chronicle, and no absolute paths except in linked-Chronicle records.

`imports/` is scratch space — a staging area for files on their way in — and does not
need backing up.
