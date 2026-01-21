# Roadmap: Astra Interview Copilot

## Milestones

- ✅ **v1.0 Latency Optimization** - Phases 1-4 (shipped)
- ✅ **v2.0 GUI & Security** - Phases 1-4 (shipped 2026-01-20)
- ✅ **v2.1 Dual-Pane Answers** - Phases 5-7 (shipped 2026-01-21)
- ✅ **v2.2 Customization** - Phase 8 (shipped 2026-01-21)

## Phases

**Phase Numbering:**
- Integer phases (5, 6, 7): Planned milestone work
- Decimal phases (5.1, 5.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 5: Dual-Pane Layout** - Vertical split with question + two answer panes
- [x] **Phase 6: Answer Formats** - Bullet points and conversational script prompts
- [x] **Phase 7: Parallel Generation** - Concurrent LLM calls for both formats
- [x] **Phase 8: Customizable Prompts & Settings** - YAML-based config for prompts, job context, tone

## Phase Details

### Phase 5: Dual-Pane Layout
**Goal**: Create vertical split UI with question display and two answer panes
**Depends on**: Nothing (first phase of v2.1)
**Requirements**: DUAL-01, DUAL-02, DUAL-03, DUAL-04
**Success Criteria** (what must be TRUE):
  1. Main window shows two answer panes side by side (vertically split)
  2. Detected question displayed at top, visible above both panes
  3. Left pane labeled for bullet points
  4. Right pane labeled for conversational script
  5. Layout responsive when window resized
**Research**: Unlikely (PyQt6 QSplitter, existing layout patterns)
**Plans**: 1 plan

Plans:
- [x] 05-01: Dual-pane layout implementation

### Phase 6: Answer Formats
**Goal**: Implement bullet point and conversational script generation prompts
**Depends on**: Phase 5 (needs UI panes to display in)
**Requirements**: FMT-01, FMT-02, FMT-03
**Success Criteria** (what must be TRUE):
  1. Bullet format produces exactly 2-3 concise key points
  2. Conversational format produces natural, speakable text
  3. Tone setting affects conversational output style
  4. Both formats use RAG context from documents
**Research**: Unlikely (prompt engineering, existing rag.py patterns)
**Plans**: 1 plan

Plans:
- [x] 06-01: Answer format prompts and generation

### Phase 7: Parallel Generation
**Goal**: Execute both LLM calls concurrently to maintain latency target
**Depends on**: Phase 6 (needs both formats defined)
**Requirements**: PAR-01, PAR-02, PAR-03
**Success Criteria** (what must be TRUE):
  1. Both LLM calls launched simultaneously (asyncio/threading)
  2. Total time from question to both answers displayed < 3 seconds
  3. Each pane updates independently when its response arrives
  4. Error in one format doesn't block the other
**Research**: Likely (async OpenAI patterns, concurrent API calls)
**Research topics**: asyncio with OpenAI SDK, concurrent futures patterns, PyQt signal threading
**Plans**: 1 plan

Plans:
- [x] 07-01: Parallel LLM execution

### Phase 8: Customizable Prompts & Settings
**Goal**: Make LLM prompts, job context, and tone configurable via YAML file
**Depends on**: Phase 7 (uses existing prompt infrastructure)
**Requirements**: CUSTOM-01, CUSTOM-02, CUSTOM-03, CUSTOM-04
**Success Criteria** (what must be TRUE):
  1. YAML config file at ~/.config/astra/prompts.yaml stores all prompts
  2. Job context input in main window affects generated answers
  3. Tone dropdown allows selection (professional, casual, confident, custom)
  4. Reload Config button refreshes settings without restart
  5. Invalid YAML gracefully falls back to defaults
**Research**: Unlikely (YAML loading, existing config patterns)
**Plans**: 1 plan

Plans:
- [x] 08-01: YAML config and GUI controls

## Progress

**Execution Order:**
Phases execute in order: 5 → 6 → 7 → 8

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 5. Dual-Pane Layout | 1/1 | Complete | 2026-01-21 |
| 6. Answer Formats | 1/1 | Complete | 2026-01-21 |
| 7. Parallel Generation | 1/1 | Complete | 2026-01-21 |
| 8. Customizable Prompts | 1/1 | Complete | 2026-01-21 |

---

<details>
<summary>✅ v2.0 GUI & Security (Phases 1-4) - SHIPPED 2026-01-20</summary>

### Phase 1: Startup Screen
**Goal**: Create a startup screen with two clear options for users
**Requirements**: GUI-01, GUI-02, GUI-03
**Plans**: 1/1 complete

### Phase 2: GUI Document Ingestion
**Goal**: Enable document ingestion through the GUI without CLI
**Requirements**: INGEST-01, INGEST-02, INGEST-03
**Plans**: 1/1 complete

### Phase 3: Resizable Layout
**Goal**: Make window resizable with horizontal layout option
**Requirements**: LAYOUT-01, LAYOUT-02
**Plans**: 1/1 complete

### Phase 4: Secure API Key Handling
**Goal**: Move API key storage to user config folder
**Requirements**: SEC-01, SEC-02, SEC-03
**Plans**: 1/1 complete

</details>

<details>
<summary>✅ v1.0 Latency Optimization & Cross-Platform - SHIPPED</summary>

- Phase 1: Memory Audio Pipeline (Complete)
- Phase 2: Transcription Optimization (Complete)
- Phase 3: Observability & Config (Deferred)
- Phase 4: Windows Compatibility & Easy Setup (Complete)

See `.planning/archive/v1.0/` for details.

</details>
