# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for Astra Interview Copilot
# Build with: pyinstaller astra.spec

import sys
from pathlib import Path

block_cipher = None

# Collect faster-whisper model files
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [
    # Include any local data files
    ('.env.example', '.'),
]

# Collect faster-whisper assets
datas += collect_data_files('faster_whisper')

# Hidden imports for PyQt6 and other packages
hiddenimports = [
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'chromadb',
    'openai',
    'numpy',
    'pdfplumber',
]

# Add Windows audio imports
if sys.platform == 'win32':
    hiddenimports.append('pyaudiowpatch')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Astra',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window for GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path if available: icon='assets/astra.ico'
)
