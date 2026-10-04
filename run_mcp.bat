@echo off
REM ---------------------------------------------------------------------
REM  ChaseLine - MCP server
REM
REM  Serves the five business tools over Streamable HTTP on
REM  127.0.0.1:8000/mcp.  Leave this window open while you use the voice
REM  simulator or the CLI agent.  Ctrl+C stops the server.
REM
REM  Double-click this file, or run:  run_mcp.bat
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

if not exist ".env" (
    echo [warn] .env not found. Copy .env.example to .env and fill it in,
    echo        otherwise the Stripe, Slack and LLM calls will fail.
    echo.
)

echo Starting the MCP server on http://127.0.0.1:8000/mcp
echo Press Ctrl+C to stop.
echo.

"%PY%" -m mcp_server.server

echo.
echo MCP server stopped.
pause
exit /b 0


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
