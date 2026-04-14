# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for Astra Interview Copilot
# Build with: pyinstaller astra.spec
# Mode: --onedir (output bundled into installer by Inno Setup)

import sys

block_cipher = None

# Collect data files for bundled packages
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata, collect_all

datas = []
binaries = []

# ---- setuptools / pkg_resources fix for ctranslate2 ----
# ctranslate2/__init__.py (Windows) does:
#     import pkg_resources
#     package_dir = pkg_resources.resource_filename(__name__, "")
#     os.add_dll_directory(package_dir)
# In Python 3.12, setuptools is no longer in venvs by default (PEP 632), and even
# when installed, PyInstaller's built-in pkg_resources hook doesn't always pull
# everything pkg_resources needs at runtime. collect_all pulls the Python code,
# binaries, data files, AND metadata — the belt-and-suspenders approach.
sp_datas, sp_binaries, sp_hiddenimports = collect_all('pkg_resources')
datas += sp_datas
binaries += sp_binaries

# Also copy ctranslate2's own package metadata so pkg_resources.resource_filename
# can locate the package directory.
datas += copy_metadata('ctranslate2')

# Bundle the pre-downloaded Whisper model (avoids huggingface_hub at runtime)
datas += [('whisper_model', 'whisper_model')]

# Collect faster-whisper assets (ONNX models, etc.)
datas += collect_data_files('faster_whisper')

# Collect chromadb data files (ONNX models, migration SQL files, etc.)
# collect_data_files captures the .sql files but NOT __init__.py stubs for
# namespace packages (subdirs without __init__.py). The runtime hook below
# registers those subdirs as importable namespace packages so
# importlib_resources.files("chromadb.migrations.*") resolves correctly.
datas += collect_data_files('chromadb')

# chromadb uses pkgutil.iter_modules() to discover embedding functions at runtime,
# which fails in frozen apps — collect all submodules so they're available.
hiddenimports = collect_submodules('chromadb')

# Many chromadb subpackages lack __init__.py — collect_submodules misses them.
# Explicitly list all runtime modules in dirs without __init__.py.
hiddenimports += [
    'chromadb.api.models.AsyncCollection',
    'chromadb.api.models.Collection',
    'chromadb.api.models.CollectionCommon',
    'chromadb.db.impl.grpc.client',
    'chromadb.db.impl.grpc.server',
    'chromadb.db.mixins.embeddings_queue',
    'chromadb.db.mixins.sysdb',
    'chromadb.execution.executor.abstract',
    'chromadb.execution.executor.distributed',
    'chromadb.execution.executor.local',
    'chromadb.execution.expression.operator',
    'chromadb.execution.expression.plan',
    'chromadb.ingest.impl.utils',
    'chromadb.logservice.logservice',
    'chromadb.segment.impl.distributed.segment_directory',
    'chromadb.segment.impl.metadata.sqlite',
    'chromadb.segment.impl.vector.batch',
    'chromadb.segment.impl.vector.brute_force_index',
    'chromadb.segment.impl.vector.hnsw_params',
    'chromadb.segment.impl.vector.local_hnsw',
    'chromadb.segment.impl.vector.local_persistent_hnsw',
    # importlib_resources — used by chromadb.db.impl.sqlite to locate migration dirs
    'importlib_resources',
    'importlib_resources.abc',
    'importlib_resources.readers',
    'importlib_resources.simple',
    'importlib_resources._adapters',
    'importlib_resources._common',
    'importlib_resources._functional',
    'importlib_resources._itertools',
    'importlib_resources.compat.py39',
]

# Additional hidden imports for PyQt6 and all v3.0 dependencies
hiddenimports += [
    # GUI framework
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    # Vector database
    'chromadb',
    # LLM client
    'openai',
    # Numerical
    'numpy',
    # PDF parsing (pure Python — no C extensions, works in frozen exe)
    'pypdf',
    # Config directory resolution
    'platformdirs',
    # License activation HTTP calls
    'requests',
    # Prompts config (pyyaml import name)
    'yaml',
    # Hybrid search (sparse retrieval)
    'rank_bm25',
    # Local modules (imported inside function bodies, PyInstaller misses them)
    'transcriber',
    'gui',
    'ingest',
    'rag',
    'config',
    'audio_capture',
    # Transcription engine
    'faster_whisper',
    'ctranslate2',
    # Environment variable loading
    'dotenv',
    # Crypto (explicit inclusion for some builds)
    'hashlib',
    'hmac',
]

# Merge in pkg_resources hidden imports from collect_all() above.
hiddenimports += sp_hiddenimports

# Add Windows audio imports
if sys.platform == 'win32':
    hiddenimports.append('pyaudiowpatch')

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    # rthook_chromadb_migrations.py: registers chromadb.migrations.* namespace
    # packages (embeddings_queue, sysdb, metadb) in sys.modules so that
    # importlib_resources.files("chromadb.migrations.embeddings_queue") resolves
    # correctly in the frozen exe. Without this, ChromaDB crashes on first DB
    # access with "No module named 'chromadb.migrations.embeddings_queue'".
    runtime_hooks=['hooks/rthook_chromadb_migrations.py'],
    excludes=[],
    # Collect chromadb as .py source files instead of compiled .pyc bytecode.
    # PyInstaller's frozen importer can interfere with chroma-hnswlib's C extension,
    # causing segfaults during HNSW index operations (GitHub #3947). Collecting as
    # source lets Python's standard import mechanism handle the modules, which
    # avoids the frozen importer conflict with the native extension.
    module_collection_mode={'chromadb': 'py'},
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# EXE launcher (binaries collected separately into dist/Astra/)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Astra',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX disabled — triggers more AV false positives than it saves
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/astra.ico',
)

# COLLECT gathers all files into dist/Astra/ — Inno Setup packages this into the installer
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Astra',
)
