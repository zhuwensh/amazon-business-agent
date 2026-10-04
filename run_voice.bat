@echo off
REM ---------------------------------------------------------------------
REM  ChaseLine - simulated Alexa+ voice experience
REM
REM  Serves the browser front end on http://127.0.0.1:8080 and talks to the
REM  MCP server at 127.0.0.1:8000/mcp.  Ctrl+C stops it.
REM
REM  Use Chrome or Edge: speech recognition is unavailable elsewhere, and
REM  the page then falls back to a type-instead box.
REM
REM  Double-click this file, or run:  run_voice.bat
REM  Or start everything at once:    run_all.bat
REM ---------------------------------------------------------------------
setlocal
cd /d "%~dp0"

call :find_python
if errorlevel 1 (
    echo.
    pause
    exit /b 1
)

call :port_open 8000
if errorlevel 1 (
    echo [warn] Nothing is listening on 127.0.0.1:8000 yet.
    echo        The page will load, but every question will fail until the
    echo        MCP server is running. Start run_mcp.bat first, or use
    echo        run_all.bat to start both.
    echo.
)

echo Starting the voice simulator on http://127.0.0.1:8080
echo Open that address in Chrome or Edge.  Press Ctrl+C to stop.
echo.

"%PY%" -m web_demo.app

echo.
echo Voice simulator stopped.
pause
exit /b 0


:port_open
REM errorlevel 0 when something is listening on 127.0.0.1:%~1
powershell -NoProfile -Command "$c = New-Object Net.Sockets.TcpClient; try { $c.Connect([ipaddress]::Loopback, %~1); $c.Close(); exit 0 } catch { exit 1 }"
exit /b %errorlevel%


:find_python
REM Prefer the project virtualenv; fall back to whatever is on PATH.
set "PY=%~dp0.venv\Scripts\python.exe"
if exist "%PY%" exit /b 0

where python >nul 2>nul
if errorlevel 1 (
    echo [error] No Python found.
    echo         Expected the project virtualenv at .venv\Scripts\python.exe
    echo.
    echo         Create it with:
    echo             python -m venv .venv
    echo             .venv\Scripts\python.exe -m pip install -r requirements.txt
    exit /b 1
)

set "PY=python"
echo [warn] .venv not found - falling back to the python on your PATH.
echo        If imports fail, run:  python -m pip install -r requirements.txt
echo.
exit /b 0
