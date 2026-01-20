@echo off
echo === Astra Interview Copilot - Windows Setup ===
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.10+ from python.org
    pause
    exit /b 1
)

REM Create virtual environment
echo Creating virtual environment...
python -m venv venv
call venv\Scripts\activate

REM Install dependencies
echo Installing dependencies...
pip install --upgrade pip
pip install -r requirements.txt

REM Check for .env
if not exist .env (
    echo.
    echo WARNING: No .env file found!
    echo Please copy .env.example to .env and add your OpenAI API key.
)

echo.
echo === Setup complete! ===
echo Run 'run.bat' to start Astra.
pause
