@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
python main.py
echo.
echo === If you see an error above, copy and paste it ===
pause
