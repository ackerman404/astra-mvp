@echo off
echo Starting Astra Interview Copilot...
echo.

if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
) else (
    echo ERROR: Virtual environment not found!
    echo Please run setup_windows.bat first.
    pause
    exit /b 1
)

python main.py %*

if errorlevel 1 (
    echo.
    echo ERROR: Application exited with an error.
    pause
)
pause
