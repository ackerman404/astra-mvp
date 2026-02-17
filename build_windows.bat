@echo off
setlocal enabledelayedexpansion

echo === Building Astra Windows Executable ===
echo.

REM Activate venv
call venv\Scripts\activate
if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment.
    echo Make sure venv exists: python -m venv venv
    pause
    exit /b 1
)

REM Install PyInstaller if needed
pip install pyinstaller
if errorlevel 1 (
    echo ERROR: Failed to install PyInstaller.
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
