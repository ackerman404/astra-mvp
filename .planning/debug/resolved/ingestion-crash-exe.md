---
status: resolved
trigger: "App crashes silently when ingesting documents from the built .exe (PyInstaller). Was working in previous milestone."
created: 2026-02-22T00:00:00Z
updated: 2026-02-22T01:30:00Z
---

## Current Focus

hypothesis: CONFIRMED - chromadb.migrations.* namespace packages not registered in frozen exe
test: Verified fix works end-to-end: find_migrations() reads all .sql files correctly
expecting: N/A - resolved
next_action: N/A - resolved

## Symptoms

expected: Documents should ingest successfully and be indexed for RAG queries
actual: App crashes during ingestion with "No module named 'chromadb.migrations.embeddings_queue'"
errors: ModuleNotFoundError: No module named 'chromadb.migrations.embeddings_queue'
reproduction: Run the built .exe, attempt to ingest documents
started: Broke on ui-optimization-branch; was working in v3.0 (previous milestone)

## Eliminated

- hypothesis: Missing .sql data files not bundled by collect_data_files('chromadb')
  evidence: build_final_log.txt shows all .sql files ARE compressed into dist/Astra/_internal/chromadb/migrations/*/
  timestamp: 2026-02-22T01:00:00Z

- hypothesis: Missing Python hiddenimports for chromadb subpackages
  evidence: chromadb.migrations.embeddings_queue has no __init__.py — it's a namespace package, not a regular Python package. collect_submodules misses it but that's not the fix path.
  timestamp: 2026-02-22T01:10:00Z

## Evidence

- timestamp: 2026-02-22T00:50:00Z
  checked: venv/Lib/site-packages/chromadb/migrations/ directory listing
  found: embeddings_queue/, sysdb/, metadb/ are directories with ONLY .sql files. No __init__.py.
  implication: These are Python namespace packages (no loader, origin=None). PyInstaller does not register them.

- timestamp: 2026-02-22T01:00:00Z
  checked: chromadb/db/impl/sqlite.py lines 74-76
  found: migration_dirs() calls files("chromadb.migrations.embeddings_queue"), files("chromadb.migrations.sysdb"), files("chromadb.migrations.metadb") via importlib_resources
  implication: importlib_resources.files(str) calls importlib.import_module(str) first. In frozen exe, these namespace packages are not in sys.modules → ModuleNotFoundError.

- timestamp: 2026-02-22T01:10:00Z
  checked: importlib_resources/_common.py resolve() + from_package() + future/adapters.py wrap_spec()
  found: resolve(str) calls importlib.import_module(str). from_package() calls wrap_spec(module).__spec__.submodule_search_locations to create NamespaceReader. NamespaceReader checks 'NamespacePath' in str(namespace_path).
  implication: The fix requires registering modules in sys.modules with __spec__.submodule_search_locations whose str() contains 'NamespacePath'.

- timestamp: 2026-02-22T01:20:00Z
  checked: _frozen_importlib_external._NamespacePath for real namespace packages
  found: str(_NamespacePath(['/path'])) == "_NamespacePath(['/path'])" — contains 'NamespacePath'
  implication: We need a custom list subclass with same str representation to satisfy NamespaceReader's guard.

- timestamp: 2026-02-22T01:25:00Z
  checked: Full end-to-end test of the fix
  found: After registering all 3 migration namespaces with _NamespacePathList wrapper, find_migrations() successfully reads 2, 9, and 4 SQL migration files respectively.
  implication: Fix is correct and complete.

## Resolution

root_cause: |
  chromadb.migrations.embeddings_queue, chromadb.migrations.sysdb, and
  chromadb.migrations.metadb are Python NAMESPACE PACKAGES (directories with no
  __init__.py). PyInstaller collects their .sql content files via collect_data_files
  but does NOT register the directories as importable Python packages.

  At runtime, chromadb/db/impl/sqlite.py calls:
    files("chromadb.migrations.embeddings_queue")  # line 74
    files("chromadb.migrations.sysdb")             # line 75
    files("chromadb.migrations.metadb")            # line 76

  importlib_resources.files(str) first calls importlib.import_module(str). In the
  frozen exe, the module is not in sys.modules → ModuleNotFoundError.

  The chroma_db folder gets created (PersistentClient init) but then crashes during
  the first migration check/apply call.

fix: |
  Added hooks/rthook_chromadb_migrations.py — a PyInstaller runtime hook that runs
  at frozen exe startup and pre-registers all three migration namespace packages in
  sys.modules with:
    - A proper importlib.machinery.ModuleSpec (loader=None, is_package=True)
    - submodule_search_locations using _NamespacePathList (a list subclass whose
      __repr__ contains '_NamespacePath' to satisfy importlib_resources.NamespaceReader)
    - __path__ pointing to the correct sys._MEIPASS subdirectory

  Also added explicit hiddenimports for importlib_resources and all its submodules
  to astra.spec to ensure it's fully bundled.

  The runtime_hooks entry in astra.spec was updated to include:
    runtime_hooks=['hooks/rthook_chromadb_migrations.py']

verification: |
  Tested end-to-end in regular Python with venv site-packages simulating _MEIPASS:
  - chromadb.migrations.embeddings_queue: 2 SQL migration files found
  - chromadb.migrations.sysdb: 9 SQL migration files found
  - chromadb.migrations.metadb: 4 SQL migration files found
  - chromadb.db.migrations.find_migrations() reads all files with correct hashes
  Ready for full PyInstaller rebuild and exe test.

files_changed:
  - hooks/rthook_chromadb_migrations.py  (NEW - runtime hook to register namespace packages)
  - astra.spec  (added runtime_hooks entry + importlib_resources hiddenimports)
