# Astra Interview Copilot

## What This Is

A desktop application that captures system audio during interviews, transcribes speech using Whisper, classifies interview questions, and generates STAR-format answers using RAG against ingested resume/documents. Built for Linux with PulseAudio/PipeWire.

## Core Value

Sub-3-second total response time from silence detection to answer display. Speed is the difference between useful real-time assistance and a distraction.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- ✓ System audio capture via PulseAudio/parec — existing
- ✓ Speech-to-text transcription via faster-whisper — existing
- ✓ LLM-based question classification (gpt-4o-mini) — existing
- ✓ RAG-based answer generation with STAR format (gpt-4o) — existing
- ✓ Document ingestion pipeline (PDF, TXT, MD → ChromaDB) — existing
- ✓ PyQt6 desktop GUI with real-time audio visualization — existing
- ✓ Auto-answer mode with silence detection and state machine — existing
- ✓ Audio device selection and configuration — existing

### Active

<!-- Current scope. Building toward these. -->

- [ ] Remove temp file I/O — keep audio in memory as numpy array
- [ ] Pass numpy array directly to faster-whisper's transcribe()
- [ ] Use beam_size=1 for faster inference
- [ ] Enable vad_filter=True to skip silence segments
- [ ] Switch to tiny.en model as default (faster inference)
- [ ] Add timing measurements in status bar (capture, transcription, RAG)
- [ ] Add config option to choose Whisper model (tiny.en, base.en, etc.)

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- Cross-platform/device agnostic support — future work, Linux optimization first
- GPU acceleration for Whisper — CPU-only for now, keep simple
- Multiple language support — English interviews only

## Context

**Existing Implementation:**
- `transcriber.py` currently writes audio to temp WAV file, loads into Whisper, then deletes
- faster-whisper already supports numpy array input and VAD filtering
- Current model is base.en (~2-3s for 30s audio)
- tiny.en is ~1s for 30s audio with slight accuracy tradeoff

**Technical Environment:**
- Linux with PipeWire/PulseAudio
- Python 3.12, PyQt6, faster-whisper, ChromaDB, OpenAI API
- Audio captured via `parec` subprocess to rolling buffer

**Codebase Analysis:**
- See `.planning/codebase/` for detailed analysis (7 documents)
- Key concerns: threading race conditions, exposed API key, no unit tests

## Constraints

- **Platform**: Linux only (PulseAudio/PipeWire dependency) — cross-platform is future work
- **Latency**: Total pipeline under 3 seconds — primary success metric
- **Accuracy**: tiny.en acceptable accuracy tradeoff for speed — can make configurable
- **Memory**: Keep audio in memory rather than disk — avoid I/O bottleneck

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| tiny.en as default model | ~1s vs ~2-3s transcription, speed is core value | — Pending |
| No temp file I/O | Eliminate disk latency, faster-whisper supports numpy arrays | — Pending |
| Timing in status bar only | Clean UI, no console clutter | — Pending |
| Linux-first optimization | Focus delivers faster than trying to be cross-platform | — Pending |

---
*Last updated: 2026-01-17 after initialization*
