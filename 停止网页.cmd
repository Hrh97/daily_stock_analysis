@echo off
setlocal
echo 正在停止股票分析工作台...
taskkill /FI "WINDOWTITLE eq DSA Web*" /T /F >nul 2>&1
if errorlevel 1 (
  echo 没有找到正在运行的服务窗口，可能已经停止。
) else (
  echo 已停止。
)
pause
