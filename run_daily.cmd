@echo off
setlocal
cd /d "%~dp0"
set "ENV_FILE=%~dp0data\runtime.env"
set "PYTHONIOENCODING=utf-8"
"%~dp0.venv\Scripts\python.exe" main.py >> "%~dp0logs\task_runner.log" 2>&1
exit /b %errorlevel%
