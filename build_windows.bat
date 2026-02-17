@echo off
setlocal enabledelayedexpansion

REM Change to the directory where this script is located
cd /d "%~dp0"

echo === Building Astra Windows Executable ===
echo.

REM Create venv if it doesn't exist
if not exist venv\Scripts\activate.bat (
    echo Virtual environment not found. Creating...
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        echo Make sure Python 3.10-3.12 is installed, or run setup_windows.bat first.
        pause
        exit /b 1
    )
)

REM Activate venv
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment.
    pause
    exit /b 1
)

REM Install dependencies and PyInstaller
echo Installing dependencies...
pip install -r requirements.txt pyinstaller
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

REM Build with PyInstaller (single-file mode via spec file)
echo Building portable executable...
pyinstaller astra.spec --clean
if errorlevel 1 (
    echo ERROR: PyInstaller build failed.
    pause
    exit /b 1
)

echo.
echo === Build complete! ===
echo Output: dist\Astra.exe
echo.
echo Users can run Astra.exe directly — no installation needed.
pause
