# Requirements: Astra Interview Copilot

**Defined:** 2026-01-17
**Core Value:** Sub-3-second total response time from silence detection to answer display

## v1 Requirements (Complete)

Requirements for latency optimization release.

### Audio Pipeline

- [x] **AUDIO-01**: Audio captured directly to numpy array in memory (no temp file)
- [x] **AUDIO-02**: Numpy array passed directly to faster-whisper transcribe()

### Transcription

- [x] **TRANS-01**: Default Whisper model switched to tiny.en (~1s for 30s audio)
- [x] **TRANS-02**: Transcription uses beam_size=1 for faster inference
- [x] **TRANS-03**: VAD filtering enabled (vad_filter=True) to skip silence segments

### Cross-Platform (v1.0)

- [x] **PLAT-02**: Support for Windows audio capture (WASAPI loopback)
- [x] **PLAT-03**: Device-agnostic audio abstraction layer

### Observability (Deferred)

- [ ] **OBS-01**: Status bar displays pipeline timing (capture, transcription, RAG duration)

### Configuration (Deferred)

- [ ] **CONFIG-01**: Config option to select Whisper model (tiny.en, base.en, small.en, etc.)

## v2 Requirements (Active)

Requirements for GUI improvements and security.

### Startup Screen

- [x] **GUI-01**: Startup screen displayed when app launches
- [x] **GUI-02**: "Ingest Documents" button on startup screen triggers document ingestion
- [x] **GUI-03**: "Start Session" button on startup screen navigates to main session screen

### Document Ingestion

- [x] **INGEST-01**: GUI-based document ingestion (no CLI required)
- [x] **INGEST-02**: Ingestion scans `documents/` folder in project directory
- [x] **INGEST-03**: Progress/status feedback during ingestion process

### Window Layout

- [ ] **LAYOUT-01**: Window is resizable (remove fixed size constraint)
- [ ] **LAYOUT-02**: Support horizontal layout option for wider screens

### Security

- [ ] **SEC-01**: API key loaded from user config folder (not project .env)
- [ ] **SEC-02**: No API keys committed to repository
- [ ] **SEC-03**: Clear user guidance for API key setup on first run

## Out of Scope

Explicitly excluded from current work.

| Feature | Reason |
|---------|--------|
| macOS support | Linux/Windows first, macOS later |
| GPU acceleration | CPU-only keeps setup simple |
| Multiple languages | English interviews only for now |
| Real-time streaming transcription | Silence-triggered batches sufficient |

## Traceability

Which phases cover which requirements. Updated by create-roadmap.

| Requirement | Phase | Status |
|-------------|-------|--------|
| AUDIO-01 | Phase 1 (v1) | Complete |
| AUDIO-02 | Phase 1 (v1) | Complete |
| TRANS-01 | Phase 2 (v1) | Complete |
| TRANS-02 | Phase 2 (v1) | Complete |
| TRANS-03 | Phase 2 (v1) | Complete |
| PLAT-02 | Phase 4 (v1) | Complete |
| PLAT-03 | Phase 4 (v1) | Complete |
| OBS-01 | - | Deferred |
| CONFIG-01 | - | Deferred |
| GUI-01 | Phase 1 (v2) | Complete |
| GUI-02 | Phase 1 (v2) | Complete |
| GUI-03 | Phase 1 (v2) | Complete |
| INGEST-01 | Phase 2 (v2) | Complete |
| INGEST-02 | Phase 2 (v2) | Complete |
| INGEST-03 | Phase 2 (v2) | Complete |
| LAYOUT-01 | Phase 3 (v2) | Pending |
| LAYOUT-02 | Phase 3 (v2) | Pending |
| SEC-01 | Phase 4 (v2) | Pending |
| SEC-02 | Phase 4 (v2) | Pending |
| SEC-03 | Phase 4 (v2) | Pending |

**Coverage:**
- v2 requirements: 11 total
- Mapped to phases: 11
- Unmapped: 0 ✓

---
*Requirements defined: 2026-01-17*
*Last updated: 2026-01-20 after Phase 2 completion*
