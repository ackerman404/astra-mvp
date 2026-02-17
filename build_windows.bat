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

REM Build with PyInstaller (--onedir mode via spec file)
echo Building executable (--onedir mode)...
pyinstaller astra.spec --clean
if errorlevel 1 (
    echo ERROR: PyInstaller build failed.
    pause
    exit /b 1
)

echo.
echo PyInstaller build complete: dist\Astra\Astra.exe
echo.

REM Check for Inno Setup compiler and build installer
where iscc >nul 2>nul
if %errorlevel%==0 (
    echo Inno Setup found. Building installer...
    iscc installer\astra_setup.iss
    if errorlevel 1 (
        echo ERROR: Inno Setup compilation failed.
        pause
        exit /b 1
    )
    echo.
    echo === Build complete! ===
    echo Executable:  dist\Astra\Astra.exe
    echo Installer:   dist\AstraSetup.exe
) else (
    echo Inno Setup (iscc.exe) not found in PATH.
    echo Skipping installer creation.
    echo To build the installer, install Inno Setup from https://jrsoftware.org/isinfo.php
    echo and add its directory to PATH, then re-run this script.
    echo.
    echo === Build complete (executable only) ===
    echo Executable:  dist\Astra\Astra.exe
)

pause
