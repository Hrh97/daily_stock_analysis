@echo off
setlocal
cd /d "%~dp0"
echo 正在打开日志目录...
if not exist "logs" mkdir "logs"
start "" explorer "%~dp0logs"
echo.
echo 最新的 web_server 日志文件名包含 web_server。
pause
