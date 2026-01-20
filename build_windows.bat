@echo off
echo === Building Astra Windows Executable ===
echo.

REM Activate venv
call venv\Scripts\activate

REM Install PyInstaller if needed
pip install pyinstaller

REM Build
echo Building executable...
pyinstaller astra.spec --clean

echo.
echo === Build complete! ===
echo Executable: dist\Astra.exe
pause
