# Chronicler Roadmap

## Phase 0 — Project foundation

* [x] Create repository structure
* [x] Configure Python package
* [x] Add development dependencies
* [x] Add formatting tools
* [x] Add linting
* [x] Add GitHub Actions CI
    * [x] Optimized multi-job workflow with caching

---

# Phase 1 — Application foundation

## Configuration

* [x] Create application settings system
* [x] Store user configuration in OS config directory
* [ ] Create first-run wizard
* [x] Select workspace location
* [x] Validate workspace permissions

---

## Backend abstraction

* [x] Define repository interfaces
* [x] Separate services from storage
* [x] Create local storage backend
* [ ] Prepare remote API backend interface

Goal:

The UI and services should not depend directly on SQLite.

---

# Phase 2 — Chronicle storage

## Archive database

* [x] Projects/Chronicles table
* [x] Tags table
* [x] Chronicle/tag relationship
* [x] Persistent task table

---

## Chronicle database

* [x] Chronicle metadata
* [x] Speakers
* [x] Transcript lines
* [ ] Cleanup state

---

# Phase 3 — Worker framework

* [x] Create worker manager
* [x] Create worker lifecycle
* [x] Persistent task handling (store tasks in master database)
* [x] Task claiming
* [x] Task status tracking: WAITING, WORKING, DONE, FAILED
* [x] Task progress tracking
* [x] Error handling
* [x] Retry support

Initial tasks:

* [ ] IMPORT
* [ ] TRANSCRIBE
* [ ] CLEAN
* [ ] EXPORT

Future:

* [ ] AI_ANALYSIS
* [ ] AI_SUMMARIZE
* [ ] GRAPH_ANALYZE

---

# Phase 4 — Desktop application

## UI

* [x] Application shell
* [x] Navigation
* [x] Theme support

---

## Archive view

* [x] Browse Chronicles
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

* [x] View active tasks
* [x] Show progress
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
* [ ] Add first run CLI wizard
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
