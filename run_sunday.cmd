@echo off
setlocal
cd /d "%~dp0"
set "ENV_FILE=%~dp0data\runtime.env"
set "PYTHONIOENCODING=utf-8"
if not exist "%~dp0logs" mkdir "%~dp0logs"
"%~dp0.venv\Scripts\python.exe" main.py --force-run >> "%~dp0logs\task_runner_sunday.log" 2>&1
exit /b %errorlevel%
