# Roadmap: Astra Interview Copilot v2.0

## Overview

Improve user experience with GUI-based document ingestion, flexible window layout, and secure API key handling. Four focused phases: startup screen, document ingestion, resizable layout, then secure configuration.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3, 4): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 1: Startup Screen** - Two-option launcher: "Ingest Documents" or "Start Session"
- [x] **Phase 2: GUI Document Ingestion** - Ingest documents from GUI with progress feedback
- [x] **Phase 3: Resizable Layout** - Remove fixed size, support horizontal layout
- [x] **Phase 4: Secure API Key Handling** - Load API key from user config, not repo

## Phase Details

### Phase 1: Startup Screen
**Goal**: Create a startup screen with two clear options for users
**Depends on**: Nothing (first phase)
**Requirements**: GUI-01, GUI-02, GUI-03
**Success Criteria** (what must be TRUE):
  1. App launches to startup screen (not directly to session)
  2. "Ingest Documents" button visible and functional
  3. "Start Session" button visible and navigates to existing session screen
  4. Session screen still fully functional after navigation
**Research**: Unlikely (standard PyQt6 patterns)
**Plans**: 1 plan

Plans:
- [x] 01-01: Startup screen implementation

### Phase 2: GUI Document Ingestion
**Goal**: Enable document ingestion through the GUI without CLI
**Depends on**: Phase 1
**Requirements**: INGEST-01, INGEST-02, INGEST-03
**Success Criteria** (what must be TRUE):
  1. Clicking "Ingest Documents" scans `documents/` folder
  2. Progress/status shown during ingestion (file count, current file)
  3. Success/error feedback displayed to user
  4. User can proceed to session after ingestion completes
**Research**: Unlikely (reuse existing ingest.py logic)
**Plans**: 1 plan

Plans:
- [x] 02-01: GUI ingestion with progress feedback

### Phase 3: Resizable Layout
**Goal**: Make window resizable with horizontal layout option
**Depends on**: Phase 1
**Requirements**: LAYOUT-01, LAYOUT-02
**Success Criteria** (what must be TRUE):
  1. Window can be resized by dragging edges/corners
  2. UI elements scale appropriately when resized
  3. Horizontal layout works on wider screens (Question left, Answer right)
  4. Minimum size enforced to prevent unusable layouts
**Research**: Unlikely (PyQt6 layout managers)
**Plans**: 1 plan

Plans:
- [x] 03-01: Resizable window with horizontal layout

### Phase 4: Secure API Key Handling
**Goal**: Move API key storage to user config folder
**Depends on**: Nothing (can be done in parallel)
**Requirements**: SEC-01, SEC-02, SEC-03
**Success Criteria** (what must be TRUE):
  1. API key loaded from user config folder (~/.config/astra/ or %APPDATA%\astra\)
  2. No .env file with API key in repo (only .env.example)
  3. First-run prompt if no API key configured
  4. Clear instructions shown to user for setup
**Research**: Unlikely (platformdirs library, standard config patterns)
**Plans**: 1 plan

Plans:
- [x] 04-01: Secure API key config implementation

## Progress

**Execution Order:**
Phases execute in order: 1 → 2 → 3 → 4
Note: Phase 3 and 4 can run in parallel after Phase 1

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Startup Screen | 1/1 | Complete | 2026-01-20 |
| 2. GUI Document Ingestion | 1/1 | Complete | 2026-01-20 |
| 3. Resizable Layout | 1/1 | Complete | 2026-01-20 |
| 4. Secure API Key Handling | 1/1 | Complete | 2026-01-19 |

## v1.0 Archive

Previous milestone (v1.0 Latency Optimization & Cross-Platform) completed phases:
- Phase 1: Memory Audio Pipeline (Complete)
- Phase 2: Transcription Optimization (Complete)
- Phase 3: Observability & Config (Deferred)
- Phase 4: Windows Compatibility & Easy Setup (Complete)

See `.planning/archive/v1.0/` for detailed phase summaries.
