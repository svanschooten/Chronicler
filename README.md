# Chronicler

> Preserve every conversation.

Chronicler is a local-first transcript management application for turning conversations into organized, searchable records.

A single recorded conversation is called a **Chronicle**.

Chronicler is designed for:

* work meetings
* interviews
* lectures
* D&D campaigns
* personal recordings
* any situation where spoken words need to become searchable knowledge

Chronicler combines transcription, organization, cleanup, and export into a single application.

---

# Concepts

## Chronicler

The application used to create, manage, and access Chronicles.

Chronicler can run in three modes:

### Desktop mode

A full local application with:

* user interface
* local storage
* local workers
* local Whisper transcription

### Server mode

A headless instance providing:

* exposes application service interfaces over API access
* project storage
* database management
* background workers
* GPU accelerated processing

### Remote mode

A lightweight instance providing:

* user interface
* consumes application service interfaces over API access
* remote storage and workers
* no local models or storage

The same codebase supports all three modes.

---

## Chronicle

A Chronicle is a self-contained record of a conversation or recording.

Examples:

* a weekly work meeting
* a D&D session
* an interview
* a lecture

A Chronicle contains:

* metadata (source, creation date, etc)
* tags
* speakers
* transcript lines

And later on can also include things like:
* related files
* generated exports
* text analysis and summaries

---

# Architecture

Chronicler separates application logic from storage.

```
             User Interface
                    |
                    |
          Application Services
                    |
        +-----------+-----------+
        |                       |
 Repository Interfaces     Remote Application Service Interfaces
        |                       |
 Local Storage             Server API
        |                       |
     SQLite                Chronicles Server
```

The application services do not know whether data is stored locally or accessed remotely.

---

# Storage

Local mode uses a user-selected workspace.

Example:

```
Chronicler/
    chronicler.db
    chronicles/
        <chronicle-id>/
            project.db
            audio/
            exports/
            logs/
```

A server installation uses the same concept:

```
/var/lib/chronicler/
    master.db
    chronicles/
```

---

# Background processing

Chronicler uses persistent background tasks.

Examples:

* importing files
* transcribing audio
* cleaning transcripts
* exporting documents
* future AI analysis

Tasks are stored persistently and survive application restarts to be restarted.

Workers execute tasks in both standalone desktop and server mode.

Remote mode will not spawn workers locally or load any models to keep package size small.

---

# Remote server

A future Chronicler Server allows users to host their own instance.

A desktop client can connect to a server using an authenticated API.

A server provides:

* centralized storage
* shared access
* GPU accelerated transcription
* background processing

Example:

```
Chronicler Desktop
        |
        | API
        |
Chronicler Server
        |
        |
   Database
   Storage
   Workers
```

A remote server is not only a transcription worker. It is a complete headless Chronicler instance.

---

# Technology stack

| Component | Technology         |
| --------- | ------------------ |
| Language  | Python             |
| UI        | Flet               |
| Database  | SQLite             |
| ORM       | SQLAlchemy         |
| API       | TBD                |
| Packaging | PyInstaller/Nuitka |
| CI/CD     | GitHub Actions     |

---

# Development setup

## Install

```
git clone git@github.com:svanschooten/Chronicler.git
cd Chronicler

python -m venv .venv

pip install -e ".[dev]"
```

---

## Run desktop application

```
python -m chronicler
```

---

## Run server mode

```
python -m chronicler server
```

---

# Future goals

* transcript editing
* custom import, export, and cleanup jobs
* audio playback synchronization
* AI summaries
* semantic search
* remote servers
* collaboration features
* additional import/export formats
