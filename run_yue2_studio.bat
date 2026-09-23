@echo off
setlocal

rem Keep every path rooted at this file so the launcher also works from a shortcut
rem or from a command prompt whose current directory is elsewhere.
set "ROOT=%~dp0"
set "PYTHON=%ROOT%venv\Scripts\python.exe"
set "COMFY_DIR=%ROOT%ComfyUI"

rem Start ComfyUI only when its API port is not already listening.
netstat -ano | findstr /R /C:":8188 .*LISTENING" >nul
if errorlevel 1 (
    start "YuE2 ComfyUI" /min /D "%COMFY_DIR%" "%ComSpec%" /d /c ""%PYTHON%" main.py --listen 127.0.0.1 --port 8188 --disable-smart-memory"
)

rem Open the studio in the default browser without holding up the server process.
start "YuE2 Browser" /b "%ComSpec%" /d /c "timeout /t 2 /nobreak >nul & start "" "http://127.0.0.1:7860""

rem The studio server stays in this window so its logs and errors remain visible.
pushd "%ROOT%"
"%PYTHON%" -m yue2_app.server
set "EXIT_CODE=%ERRORLEVEL%"
popd
endlocal & exit /b %EXIT_CODE%
