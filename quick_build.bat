@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat

if not exist whisper_model\model.bin (
    echo Downloading Whisper model ^(tiny.en^)...
    python -c "from huggingface_hub import snapshot_download; snapshot_download('Systran/faster-whisper-tiny.en', local_dir='whisper_model')"
)

echo Quick rebuild (no clean, console enabled for debugging)...
pyinstaller astra.spec
echo.
echo Done. Run dist\Astra\Astra.exe from a command prompt to see errors.
pause
