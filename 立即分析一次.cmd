@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=%~dp0.venv\Scripts\python.exe"
set "ENV_FILE=%~dp0data\runtime.env"
set "PYTHONIOENCODING=gbk:replace"

if not exist "%PYTHON%" (
  echo [错误] 没找到 Python 虚拟环境。
  pause
  exit /b 1
)

echo 即将对自选股执行一次完整分析并推送到钉钉。
echo 这会消耗模型额度，通常需要 3 到 10 分钟。
choice /C YN /M "确认现在开始吗"
if errorlevel 2 (
  echo 已取消。
  pause
  exit /b 0
)

echo.
echo 开始分析，请勿关闭本窗口...
"%PYTHON%" main.py
echo.
echo 分析结束。详细结果可在 127.0.0.1:8000 查看。
pause
