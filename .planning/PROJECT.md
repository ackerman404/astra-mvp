# Astra Interview Copilot

## What This Is

A desktop application that captures system audio during interviews, transcribes speech using Whisper, classifies interview questions, and generates STAR-format answers using RAG against ingested resume/documents. Works on both Linux and Windows.

## Core Value

Sub-3-second total response time from silence detection to answer display. Speed is the difference between useful real-time assistance and a distraction.

## Current Milestone: v2.1 Dual-Pane Answers

**Goal:** Display two answer formats simultaneously — quick bullet points and conversational script — with parallel LLM generation to maintain sub-3-second latency.

**Target features:**
- Dual-pane vertical split layout (bullets left, script right)
- Question display at top of answer area
- Quick 2-3 bullet point summary for rapid reference
- Humanized conversational script with configurable tone
- Parallel LLM calls for both outputs without latency hit

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

- [ ] Dual-pane vertical split layout (bullet points + conversational script)
- [ ] Question display at top of answer area
- [ ] Parallel LLM generation (two agents, no latency hit)
- [ ] Quick bullet point format (2-3 key points)
- [ ] Conversational script format (humanized, tone-configurable)

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

**v2.0 Shipped:**
- Startup screen with Ingest/Start options
- GUI-based document ingestion with progress
- Resizable window with horizontal layout
- Secure API key handling (platformdirs)

**Current Issues:**
- Single answer format (STAR only)
- Sequential LLM calls (one output at a time)
- No question display in answer area

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
*Last updated: 2026-01-21 after v2.1 milestone start*
