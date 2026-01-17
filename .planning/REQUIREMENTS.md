# Requirements: Astra Interview Copilot

**Defined:** 2026-01-17
**Core Value:** Sub-3-second total response time from silence detection to answer display

## v1 Requirements

Requirements for latency optimization release.

### Audio Pipeline

- [ ] **AUDIO-01**: Audio captured directly to numpy array in memory (no temp file)
- [ ] **AUDIO-02**: Numpy array passed directly to faster-whisper transcribe()

### Transcription

- [ ] **TRANS-01**: Default Whisper model switched to tiny.en (~1s for 30s audio)
- [ ] **TRANS-02**: Transcription uses beam_size=1 for faster inference
- [ ] **TRANS-03**: VAD filtering enabled (vad_filter=True) to skip silence segments

### Observability

- [ ] **OBS-01**: Status bar displays pipeline timing (capture, transcription, RAG duration)

### Configuration

- [ ] **CONFIG-01**: Config option to select Whisper model (tiny.en, base.en, small.en, etc.)

## v2 Requirements

Deferred to future release.

### Cross-Platform

- **PLAT-01**: Support for macOS audio capture
- **PLAT-02**: Support for Windows audio capture
- **PLAT-03**: Device-agnostic audio abstraction layer

### Performance

- **PERF-01**: GPU acceleration for Whisper (CUDA support)
- **PERF-02**: Batch transcription for long audio segments

### Localization

- **LOC-01**: Support for non-English interview transcription

## Out of Scope

Explicitly excluded from current work.

| Feature | Reason |
|---------|--------|
| Cross-platform support | Linux optimization first, future work |
| GPU acceleration | CPU-only keeps setup simple |
| Multiple languages | English interviews only for now |
| Real-time streaming transcription | Silence-triggered batches sufficient |

## Traceability

Which phases cover which requirements. Updated by create-roadmap.

| Requirement | Phase | Status |
|-------------|-------|--------|
| AUDIO-01 | — | Pending |
| AUDIO-02 | — | Pending |
| TRANS-01 | — | Pending |
| TRANS-02 | — | Pending |
| TRANS-03 | — | Pending |
| OBS-01 | — | Pending |
| CONFIG-01 | — | Pending |

**Coverage:**
- v1 requirements: 7 total
- Mapped to phases: 0
- Unmapped: 7 ⚠️ (awaiting roadmap)

---
*Requirements defined: 2026-01-17*
*Last updated: 2026-01-17 after initial definition*
