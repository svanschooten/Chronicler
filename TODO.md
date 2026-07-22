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
* [x] Create first-run wizard
* [x] Select workspace location
* [x] Validate workspace permissions
* [x] Automatic configuration validation for different run modes

## Architecture alignment

* [ ] Implement DI container for service resolution
* [ ] Refactor DesktopApp to use DI container
* [ ] Support switching between local and remote services based on settings
* [ ] Ensure all business logic is strictly in Services

---

## Backend abstraction

* [x] Define repository interfaces
* [x] Separate services from storage
* [x] Create local storage backend
* [x] Prepare remote API backend interface

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
* [ ] Tags (in project.db for portability)
* [ ] AI analysis results
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
* [ ] Implement annotation-based provider registration
* [ ] Implement Scribe workers with concurrency configuration

Initial tasks:

* [x] IMPORT
* [ ] TRANSCRIBE
* [x] CLEAN
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
* [ ] Implement SearchService
    * [ ] Workspace search (across chronicles)
    * [ ] Chronicle search (Full-text search using SQLite FTS)
* [ ] Search UI in Archive view
* [ ] Filter by tags
* [ ] Open Chronicle
* [x] Import Transcript (via Header)

---

## Create Chronicle wizard

* [x] Select files
* [ ] Assign speakers
* [ ] Enter metadata
* [ ] Add tags
* [x] Create Chronicle (Basic implementation)

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
* [x] Import worker
* [x] Regex importer

---

## Transcription

* [ ] Whisper integration
* [ ] Transcription worker
* [ ] Timestamp handling
* [ ] Speaker assignment
* [ ] Retry support

---

## Cleanup

* [x] Cleanup worker
* [x] Text normalization
* [x] Segment merging
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
* [x] Add server application mode
* [x] Add first run CLI wizard
    * [x] Add option to generate or set API key
* [x] Add API layer
* [x] Add authentication
* [ ] Add server storage management
* [x] Add remote repository implementation
* [ ] Connect desktop client to server

---

# Phase 8 — Web Client

* [x] Implement basic web client server
* [x] Serve static files
* [x] Implement API proxy or CORS support for Chronicler Server
* [x] Web Client Configuration in Wizard (Option to set up as a Web Client server)
* [ ] Basic UI for browsing Chronicles
* [ ] Basic UI for viewing a Chronicle

---

# Phase 9 — Distribution

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
