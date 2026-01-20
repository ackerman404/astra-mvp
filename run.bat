@echo off
if exist venv\Scripts\activate (
    call venv\Scripts\activate
)
python main.py %*
