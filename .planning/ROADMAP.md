# Roadmap: Astra Interview Copilot

## Overview

Optimize the audio-to-answer pipeline from ~3-5 seconds down to sub-3-second latency. Three focused phases: eliminate temp file I/O, speed up Whisper inference, then add timing visibility and configurability.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 1: Memory Audio Pipeline** - Eliminate temp file I/O, keep audio in numpy arrays
- [x] **Phase 2: Transcription Optimization** - Faster Whisper with tiny.en model and VAD
- [ ] **Phase 3: Observability & Config** - Timing display and model selection
- [x] **Phase 4: Windows Compatibility & Easy Setup** - Making it work on Windows, easy to setup and run

## Phase Details

### Phase 1: Memory Audio Pipeline
**Goal**: Eliminate temp file I/O, keep audio in numpy arrays
**Depends on**: Nothing (first phase)
**Requirements**: AUDIO-01, AUDIO-02
**Success Criteria** (what must be TRUE):
  1. Audio capture stores data directly in numpy array (no temp file written)
  2. Numpy array passed to faster-whisper without intermediate file
  3. Existing functionality still works (transcription produces text)
**Research**: Unlikely (faster-whisper already supports numpy input)
**Plans**: 1 plan

Plans:
- [x] 01-01: Memory audio pipeline implementation

### Phase 2: Transcription Optimization
**Goal**: Faster Whisper inference with tiny.en and VAD
**Depends on**: Phase 1
**Requirements**: TRANS-01, TRANS-02, TRANS-03
**Success Criteria** (what must be TRUE):
  1. Default model is tiny.en (not base.en)
  2. Transcription uses beam_size=1
  3. VAD filtering skips silence segments
  4. Transcription latency reduced (measurable improvement)
**Research**: Unlikely (documented params: beam_size, vad_filter)
**Plans**: 1 plan

Plans:
- [x] 02-01: Transcription optimization implementation

### Phase 3: Observability & Config
**Goal**: Timing visibility and model selection
**Depends on**: Phase 2
**Requirements**: OBS-01, CONFIG-01
**Success Criteria** (what must be TRUE):
  1. Status bar shows capture/transcription/RAG timing
  2. User can select Whisper model from config
  3. Model selection affects transcription behavior
**Research**: Unlikely (internal UI and config patterns)
**Plans**: TBD

Plans:
- [ ] 03-01: Timing display and model config

### Phase 4: Windows Compatibility & Easy Setup
**Goal**: Making it work on Windows, easy to setup and run
**Depends on**: Phase 3
**Requirements**: PLAT-02 (Windows audio capture)
**Success Criteria** (what must be TRUE):
  1. Application runs on Windows without code modification
  2. Audio capture works on Windows via WASAPI loopback
  3. Simple setup process (one-click scripts)
  4. Easy to run (single command or executable)
**Research**: Complete (PyAudioWPatch for WASAPI, PyInstaller for packaging)
**Plans**: 3 plans in 3 waves

Plans:
- [x] 04-01: Audio abstraction layer + Linux refactor
- [x] 04-02: Windows audio backend (WASAPI)
- [x] 04-03: Easy setup scripts + packaging

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Memory Audio Pipeline | 1/1 | Complete | 2026-01-17 |
| 2. Transcription Optimization | 1/1 | Complete | 2026-01-17 |
| 3. Observability & Config | 0/1 | Not started | - |
| 4. Windows Compatibility & Easy Setup | 3/3 | Complete | 2026-01-20 |
