# Chronicler Roadmap

## Phase 0 — Project foundation

* [x] Create repository structure
* [ ] Configure Python package
* [ ] Add development dependencies
* [ ] Add formatting tools
* [ ] Add linting
* [ ] Add GitHub Actions CI

---

# Phase 1 — Application foundation

## Configuration

* [ ] Create application settings system
* [ ] Store user configuration in OS config directory
* [ ] Create first-run wizard
* [ ] Select workspace location
* [ ] Validate workspace permissions

---

## Backend abstraction

* [ ] Define repository interfaces
* [ ] Separate services from storage
* [ ] Create local storage backend
* [ ] Prepare remote API backend interface

Goal:

The UI and services should not depend directly on SQLite.

---

# Phase 2 — Chronicle storage

## Archive database

* [ ] Projects/Chronicles table
* [ ] Tags table
* [ ] Chronicle/tag relationship
* [ ] Persistent task table

---

## Chronicle database

* [ ] Chronicle metadata
* [ ] Speakers
* [ ] Transcript lines
* [ ] Cleanup state

---

# Phase 3 — Worker framework

* [ ] Create worker manager
* [ ] Create worker lifecycle
* [ ] Persistent task handling
* [ ] Task claiming
* [ ] Task status tracking
* [ ] Error handling
* [ ] Retry support

Initial tasks:

* [ ] IMPORT
* [ ] TRANSCRIBE
* [ ] CLEAN
* [ ] EXPORT

Future:

* [ ] AI_ANALYSIS

---

# Phase 4 — Desktop application

## UI

* [ ] Application shell
* [ ] Navigation
* [ ] Theme support

---

## Archive view

* [ ] Browse Chronicles
* [ ] Search
* [ ] Filter by tags
* [ ] Open Chronicle

---

## Create Chronicle wizard

* [ ] Select files
* [ ] Assign speakers
* [ ] Enter metadata
* [ ] Add tags
* [ ] Create Chronicle

---

## Task monitor

* [ ] View active tasks
* [ ] Show progress
* [ ] Retry failures

---

# Phase 5 — Processing

## Import

* [ ] Audio importer
* [ ] File validation
* [ ] Import worker

---

## Transcription

* [ ] Whisper integration
* [ ] Transcription worker
* [ ] Timestamp handling
* [ ] Speaker assignment
* [ ] Retry support

---

## Cleanup

* [ ] Cleanup worker
* [ ] Text normalization
* [ ] Segment merging
* [ ] Cleanup markers

---

# Phase 6 — Editing and export

## Transcript viewer

* [ ] Display transcript
* [ ] Edit text
* [ ] Search within Chronicle

Future:

* [ ] Audio synchronization
* [ ] Timestamp editing

---

## Export

Initial:

* [ ] Plain text export
* [ ] Markdown export

Future:

* [ ] PDF
* [ ] DOCX
* [ ] HTML

---

# Phase 7 — Chronicler Server

* [ ] Add server application mode
* [ ] Add API layer
* [ ] Add authentication
* [ ] Add server storage management
* [ ] Add remote repository implementation
* [ ] Connect desktop client to server

---

# Phase 8 — Distribution

* [ ] GitHub Actions builds
* [ ] Automated releases
* [ ] Windows package
* [ ] macOS package
* [ ] Linux package

Possible tools:

* PyInstaller
* Nuitka

---

# Future ideas

## Collaboration

* [ ] Multiple users
* [ ] Permissions
* [ ] Shared Chronicles
* [ ] Conflict handling

## Intelligence

* [ ] Summaries
* [ ] Action items
* [ ] Topic extraction
* [ ] Semantic search
* [ ] Embeddings
