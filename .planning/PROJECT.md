# Astra Interview Copilot

## What This Is

A desktop application that captures system audio during interviews, transcribes speech using Whisper, classifies interview questions, and generates STAR-format answers using RAG against ingested resume/documents. Works on both Linux and Windows.

## Core Value

Sub-3-second total response time from silence detection to answer display. Speed is the difference between useful real-time assistance and a distraction.

## Current Milestone: v2.0 GUI & Security

**Goal:** Improve user experience with GUI-based document ingestion, flexible layout, and secure API key handling.

**Target features:**
- Startup screen with "Ingest Documents" and "Start Session" options
- Document ingestion from GUI (scans documents/ folder)
- Resizable window with horizontal layout support
- Secure API key handling (not exposed in repo)

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- ✓ System audio capture via PulseAudio/parec — v1.0
- ✓ Windows audio capture via WASAPI — v1.0
- ✓ Speech-to-text transcription via faster-whisper — v1.0
- ✓ LLM-based question classification (gpt-4o-mini) — existing
- ✓ RAG-based answer generation with STAR format (gpt-4o) — existing
- ✓ Document ingestion pipeline (PDF, TXT, MD → ChromaDB) — existing
- ✓ PyQt6 desktop GUI with real-time audio visualization — existing
- ✓ Auto-answer mode with silence detection and state machine — existing
- ✓ Audio device selection and configuration — existing
- ✓ Memory audio pipeline (numpy arrays, no temp files) — v1.0
- ✓ Transcription optimization (tiny.en, VAD, beam_size=1) — v1.0
- ✓ Cross-platform support (Linux + Windows) — v1.0
- ✓ Easy setup scripts (setup_windows.bat, run.bat, run.sh) — v1.0

### Active

<!-- Current scope. Building toward these. -->

- [ ] Startup screen with two options: "Ingest Documents" / "Start Session"
- [ ] GUI-based document ingestion (scans documents/ folder)
- [ ] Resizable window with horizontal layout support
- [ ] Secure API key handling (load from user config, not in repo)

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- GPU acceleration for Whisper — CPU-only keeps setup simple
- Multiple language support — English interviews only for now
- Real-time streaming transcription — Silence-triggered batches work well

## Context

**v1.0 Shipped:**
- Memory audio pipeline eliminates temp file I/O
- Transcription uses tiny.en with VAD for speed
- Cross-platform audio capture abstraction
- Windows WASAPI backend via PyAudioWPatch
- Setup scripts for easy installation

**Technical Environment:**
- Python 3.12, PyQt6, faster-whisper, ChromaDB, OpenAI API
- Linux: PulseAudio/PipeWire via parec
- Windows: WASAPI loopback via PyAudioWPatch

**Current Issues:**
- Document ingestion only via CLI (--ingest flag)
- Fixed window size, no horizontal layout
- API key in .env file (should be in user config folder)

## Constraints

- **Platform**: Linux and Windows
- **Latency**: Total pipeline under 3 seconds
- **Security**: API keys must not be committed to repo

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| tiny.en as default model | ~1s vs ~2-3s transcription, speed is core value | ✓ Good |
| No temp file I/O | Eliminate disk latency | ✓ Good |
| Abstract AudioCapture interface | Clean cross-platform support | ✓ Good |
| PyAudioWPatch for Windows | WASAPI loopback for system audio | ✓ Good |
| Factory pattern for platform detection | sys.platform based selection | ✓ Good |

---
*Last updated: 2026-01-20 after v2.0 milestone start*
