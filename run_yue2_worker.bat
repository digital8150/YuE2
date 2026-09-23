@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON=%ROOT%venv\Scripts\python.exe"
set "COMFY_DIR=%ROOT%ComfyUI"
if exist "%ROOT%.yue2-worker.local.bat" call "%ROOT%.yue2-worker.local.bat"

if not defined YUE2_SERVER_URL set "YUE2_SERVER_URL=https://yue.codingbot.kr"
if not defined YUE2_WORKER_ID set "YUE2_WORKER_ID=local-4070ti"
if not defined YUE2_WORKER_TOKEN (
    echo Set YUE2_WORKER_TOKEN before starting this worker.
    exit /b 1
)

netstat -ano | findstr /R /C:":8188 .*LISTENING" >nul
if errorlevel 1 (
    start "YuE2 ComfyUI" /min /D "%COMFY_DIR%" "%ComSpec%" /d /c ""%PYTHON%" main.py --listen 127.0.0.1 --port 8188 --disable-smart-memory"
)
pushd "%ROOT%"
"%PYTHON%" -m yue2_app.worker
set "EXIT_CODE=%ERRORLEVEL%"
popd
endlocal & exit /b %EXIT_CODE%
