---
status: resolved
trigger: "Document ingestion crashes with ChromaDB telemetry error during collection creation"
created: 2026-02-21T00:00:00Z
updated: 2026-02-21T00:05:00Z
---

## Current Focus

hypothesis: RESOLVED
test: N/A
expecting: N/A
next_action: N/A

## Symptoms

expected: Documents should be ingested into ChromaDB successfully (PDF files, 90-166MB total)
actual: Ingestion fails and the app crashes/shows error
errors: "Ingestion failed: Failed to send telemetry event ClientCreateCollectionEvent: capture() takes 1 positional argument but 3 were given"
reproduction: Try to ingest documents (4 PDFs, 166MB total, or even a single 90MB PDF) via the Ingest Documents button in the Astra app
started: After recent changes — ingestion code was modified to use PyMuPDF instead of pdfplumber, and to run in a subprocess. ChromaDB version may have a compatibility issue with its telemetry/posthog dependency.

## Eliminated

- hypothesis: "The crash happens due to subprocess communication issues in the new ingestion flow"
  evidence: Error is clearly a TypeError in posthog capture() call, not a subprocess communication error
  timestamp: 2026-02-21T00:01:00Z

- hypothesis: "Setting anonymized_telemetry=False in Settings is sufficient to suppress the error"
  evidence: Even with anonymized_telemetry=False, chromadb still calls _direct_capture() which calls posthog.capture() with 3 positional args — the TypeError fires before posthog can check the disabled flag
  timestamp: 2026-02-21T00:03:00Z

## Evidence

- timestamp: 2026-02-21T00:00:30Z
  checked: chromadb and posthog installed versions in venv
  found: chromadb==0.6.3, posthog==7.9.1
  implication: posthog 7.9.1 is a very new version (breaking change happened at 6.0)

- timestamp: 2026-02-21T00:00:45Z
  checked: venv/Lib/site-packages/posthog/__init__.py capture() function signature
  found: "def capture(event: str, **kwargs)" — only 1 positional arg (event). Comment in code explicitly says this was a BREAKING CHANGE from posthog 5.x to 6.0+. Old API was capture(distinct_id, event, properties).
  implication: ChromaDB 0.6.3 calls posthog.capture(user_id, event_name, properties_dict) with 3 positional args, which fails with posthog 6.0+

- timestamp: 2026-02-21T00:00:50Z
  checked: venv/Lib/site-packages/chromadb/telemetry/product/posthog.py _direct_capture method
  found: posthog.capture(self.user_id, event.name, {**event.properties, ...}) — calls with 3 positional args
  implication: This is the exact call that fails. The error is caught and logged, but the error message surfaces to the user.

- timestamp: 2026-02-21T00:04:00Z
  checked: posthog 5.4.0 capture() signature after downgrade
  found: capture(distinct_id, event, properties=None, context=None, ...) — old 3-positional-arg API restored
  implication: Downgrading to posthog<6.0.0 resolves the compatibility issue

- timestamp: 2026-02-21T00:04:30Z
  checked: Live test — chromadb.PersistentClient + get_or_create_collection with posthog 5.4.0
  found: "SUCCESS: Collection created: test_collection / No telemetry crash"
  implication: Fix is verified

## Resolution

root_cause: posthog broke its API in v6.0 — module-level `capture(distinct_id, event, properties)` became `capture(event, **kwargs)` (distinct_id now keyword-only). ChromaDB 0.6.3 still calls the old 3-positional-arg API in its telemetry's `_direct_capture()` method. chromadb 0.6.3's METADATA only specifies `posthog>=2.4.0` (no upper bound), so pip installed the incompatible posthog 7.9.1.
fix: |
  1. Downgraded posthog from 7.9.1 to 5.4.0 (last compatible series) in venv
  2. Added `posthog>=2.4.0,<6.0.0` pin to requirements.txt to prevent re-occurrence
  3. Added `settings=chromadb.Settings(anonymized_telemetry=False)` to all PersistentClient() calls in ingest.py and rag.py as defense-in-depth (disables telemetry entirely)
verification: Ran chromadb.PersistentClient() + get_or_create_collection() in venv — clean exit, no telemetry errors, collection created successfully
files_changed:
  - ingest.py (PersistentClient now passes anonymized_telemetry=False settings)
  - rag.py (both PersistentClient calls now pass anonymized_telemetry=False settings)
  - requirements.txt (pinned posthog>=2.4.0,<6.0.0)
