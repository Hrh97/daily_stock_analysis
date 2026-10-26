@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=%~dp0.venv\Scripts\python.exe"
set "ENV_FILE=%~dp0data\runtime.env"
set "PYTHONIOENCODING=gbk:replace"

if not exist "%PYTHON%" (
  echo [错误] 没找到 Python 虚拟环境。
  echo 请先联系部署人重新安装依赖。
  pause
  exit /b 1
)
if not exist "%~dp0static\index.html" (
  echo [错误] 没找到 Web 界面静态文件，请先构建前端。
  pause
  exit /b 1
)

netstat -ano | findstr /R /C:"127.0.0.1:8000 .*LISTENING" >nul
if not errorlevel 1 (
  echo 服务已经在运行，直接打开网页。
  start "" "http://127.0.0.1:8000"
  pause
  exit /b 0
)

echo 正在启动股票分析工作台，请稍候...
start "DSA Web" /min "%PYTHON%" webui.py

powershell -NoProfile -ExecutionPolicy Bypass -Command "for($i=0;$i -lt 60;$i++){ try { $r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:8000/api/health; if($r.StatusCode -eq 200){ exit 0 } } catch {}; Start-Sleep -Seconds 1 }; exit 1"
if errorlevel 1 (
  echo [错误] 服务 60 秒内没有启动成功。
  echo 请双击 查看日志.cmd 查看报错。
  pause
  exit /b 1
)

echo 启动成功：http://127.0.0.1:8000
start "" "http://127.0.0.1:8000"
echo 本窗口可以关闭，后台服务会继续运行。
pause
