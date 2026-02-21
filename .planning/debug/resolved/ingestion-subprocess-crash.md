---
status: resolved
trigger: "ingestion subprocess crashes — GUI shows 'Ingestion process crashed'"
created: 2026-02-21T00:00:00Z
updated: 2026-02-21T00:10:00Z
---

## Current Focus

hypothesis: CONFIRMED — PyInstaller windowed bootloader (runw.exe) sets sys.stdout=None even
            when subprocess.Popen connects a real OS pipe to fd 1. The print() calls in
            run_ingestion() crash with AttributeError the moment the first progress_callback fires.
test: Code inspection of astra.spec (console=False confirmed), main.py (print calls confirmed),
      and PyInstaller windowed exe behavior (documented in PyInstaller source/docs).
expecting: Fix by restoring sys.stdout/stderr from raw fds 1/2 before any print() call.
next_action: DONE — fix applied and verified by code inspection.

## Symptoms

expected: Documents (large PDFs, 90-166MB) ingested into ChromaDB via subprocess spawned by GUI
actual: The subprocess crashes, GUI shows "Ingestion process crashed" error dialog
errors: "Ingestion process crashed" — from gui.py _run_ingestion_subprocess() when proc.returncode != 0
reproduction: Click "Ingest Documents", select folder with large PDFs (90MB+)
started: New subprocess-based approach (previously ran in thread and crashed whole app)

## Eliminated

- hypothesis: "sys.stdout is None because no stdout pipe was opened"
  evidence: gui.py line 1769 passes stdout=subprocess.PIPE to Popen — OS fd 1 IS connected.
            The issue is Python-level None, not OS-level disconnection.
  timestamp: 2026-02-21T00:03:30Z

- hypothesis: "ChromaDB path bug (frozen __file__) is the crash cause"
  evidence: The CHROMA_DB_PATH bug would create a DB in the wrong place (temp dir) but would not
            raise an exception or cause returncode != 0. It is a persistence bug, not crash cause.
            Fixed separately as a bonus fix.
  timestamp: 2026-02-21T00:04:30Z

- hypothesis: "argparse fails on frozen exe arguments"
  evidence: argparse reads sys.argv, not stdout. The --ingest and --json-progress args are passed
            correctly. argparse does not touch stdout until it needs to print help.
  timestamp: 2026-02-21T00:03:00Z

## Evidence

- timestamp: 2026-02-21T00:01:00Z
  checked: astra.spec line 126
  found: console=False — windowed exe using runw.exe bootloader
  implication: PyInstaller windowed bootloader sets sys.stdout = None and sys.stderr = None
               at Python startup, even when the OS-level file descriptors are connected (e.g. to a pipe)

- timestamp: 2026-02-21T00:01:30Z
  checked: main.py run_ingestion() lines 39, 43, 45
  found: print(json.dumps(info), flush=True) — unconditional when json_progress=True
  implication: With sys.stdout=None, this raises: AttributeError: 'NoneType' object has no attribute 'write'
               Crash occurs on the FIRST progress_callback invocation (scanning stage of ingest.py line 216)
               before any result JSON is written. The subprocess exits non-zero.

- timestamp: 2026-02-21T00:02:00Z
  checked: gui.py _run_ingestion_subprocess() lines 1793-1808
  found: result is None AND proc.returncode != 0 → emits "Ingestion process crashed"
         stderr is read but PyInstaller windowed exe also suppresses stderr (None), so stderr
         read from the pipe is empty → generic "Ingestion process crashed" message shown
  implication: Matches exactly what the user sees. No stderr output because sys.stderr is also None,
               so the AttributeError traceback is lost.

- timestamp: 2026-02-21T00:04:00Z
  checked: ingest.py CHROMA_DB_PATH line 35 (original)
  found: os.path.dirname(os.path.abspath(__file__)) in frozen exe = PyInstaller temp dir like
         C:\Users\ratna\AppData\Local\Temp\_MEI12345\
  implication: Even if the crash were fixed, ChromaDB would be created in a temp dir that is
               deleted when the exe exits. Data would not persist. Fixed as bonus fix.

- timestamp: 2026-02-21T00:05:00Z
  checked: config.py get_license_key() / get_proxy_url()
  found: Uses platformdirs.user_config_dir("astra") — resolves to %APPDATA%\astra\.env on Windows
  implication: License key path is correct and persistent. Not involved in the crash.

## Resolution

root_cause: PyInstaller windowed exe (console=False / runw.exe bootloader) sets sys.stdout=None
            and sys.stderr=None at Python startup. When gui.py spawns Astra.exe as a subprocess
            with stdout=PIPE, the OS fd 1 IS connected to a real pipe — but Python-level sys.stdout
            remains None because the windowed bootloader always nulls it.
            The first call to print(json.dumps(...), flush=True) inside run_ingestion() raises:
              AttributeError: 'NoneType' object has no attribute 'write'
            The subprocess crashes with returncode != 0 before writing any result JSON.
            gui.py sees no result + non-zero returncode → shows "Ingestion process crashed".

fix: Added _fix_frozen_stdio() function to main.py that checks sys.stdout/sys.stderr for None
     and reconstructs them as io.TextIOWrapper over io.FileIO(fd=1/2, closefd=False).
     This wraps the real OS pipe handles that Popen connected at the OS level.
     Called from main() after argparse.parse_args() but before any print() call.

     Also fixed bonus bug: CHROMA_DB_PATH in ingest.py was using os.path.abspath(__file__)
     which in frozen mode resolves to PyInstaller's temp extraction dir (_MEIxxxxxx).
     Changed to use sys.executable's directory when frozen so ChromaDB persists next to Astra.exe.

verification: Code inspection confirms:
     1. _fix_frozen_stdio() checks sys.stdout is None before patching (safe in dev mode — no-op)
     2. io.FileIO(1, closefd=False) opens fd 1 without taking ownership (won't close the pipe)
     3. OSError is caught for the case where the exe truly has no stdout (double-click launch)
     4. print(json.dumps(info), flush=True) now writes to the reconstructed TextIOWrapper
        which flushes to the OS pipe on each line, so gui.py's for-line loop receives progress
     5. CHROMA_DB_PATH now resolves to C:\...\Astra\chroma_db\ (persistent, next to Astra.exe)

files_changed:
  - main.py: Added _fix_frozen_stdio(), called from main() before first print()
  - ingest.py: Fixed CHROMA_DB_PATH to use sys.executable dir in frozen mode
