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

## v2.1 Requirements (Active)

Requirements for dual-pane answer display with parallel generation.

### Dual-Pane Layout

- [x] **DUAL-01**: Vertical split layout with two answer panes side by side
- [x] **DUAL-02**: Question displayed at top of answer area (visible in both contexts)
- [x] **DUAL-03**: Left pane displays bullet point summary
- [x] **DUAL-04**: Right pane displays conversational script

### Answer Formats

- [x] **FMT-01**: Bullet point format produces 2-3 key points maximum
- [x] **FMT-02**: Conversational script is humanized and readable aloud
- [x] **FMT-03**: Script tone is configurable (professional, casual, confident)

### Parallel Generation

- [x] **PAR-01**: Both answer formats generated via parallel LLM calls
- [x] **PAR-02**: Total latency remains under 3 seconds (no sequential hit)
- [x] **PAR-03**: Both panes update when their respective response arrives

---

## v2 Requirements (Complete)

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

- [x] **LAYOUT-01**: Window is resizable (remove fixed size constraint)
- [x] **LAYOUT-02**: Support horizontal layout option for wider screens

### Security

- [x] **SEC-01**: API key loaded from user config folder (not project .env)
- [x] **SEC-02**: No API keys committed to repository
- [x] **SEC-03**: Clear user guidance for API key setup on first run

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
| LAYOUT-01 | Phase 3 (v2) | Complete |
| LAYOUT-02 | Phase 3 (v2) | Complete |
| SEC-01 | Phase 4 (v2) | Complete |
| SEC-02 | Phase 4 (v2) | Complete |
| SEC-03 | Phase 4 (v2) | Complete |

**v2 Coverage:**
- v2 requirements: 11 total
- Mapped to phases: 11
- Unmapped: 0 ✓

---

## v2.1 Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DUAL-01 | Phase 5 | Complete |
| DUAL-02 | Phase 5 | Complete |
| DUAL-03 | Phase 5 | Complete |
| DUAL-04 | Phase 5 | Complete |
| FMT-01 | Phase 6 | Complete |
| FMT-02 | Phase 6 | Complete |
| FMT-03 | Phase 6 | Complete |
| PAR-01 | Phase 7 | Complete |
| PAR-02 | Phase 7 | Complete |
| PAR-03 | Phase 7 | Complete |

**v2.1 Coverage:**
- v2.1 requirements: 10 total
- Mapped to phases: 10
- Unmapped: 0 ✓

---
*Requirements defined: 2026-01-17*
*Last updated: 2026-01-21 after Phase 5 completion*
