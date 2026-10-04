@echo off
REM ---------------------------------------------------------------------
REM  ChaseLine - start everything, then open the browser
REM
REM  Opens two windows: the MCP server (:8000) and the voice simulator
REM  (:8080).  Each one is waited on until it really accepts connections,
REM  so the first page load already works.
REM
REM  Anything already listening on :8000 or :8080 is reused instead of
REM  started twice, so running this twice is harmless.
REM
REM  Close the two new windows (or press Ctrl+C in each) to stop the demo.
REM ---------------------------------------------------------------------
setlocal
cd /d "%~dp0"
set "FAILED="

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
    set "FAILED=1"
)

echo ============================================================
echo   ChaseLine - starting the demo
echo ============================================================
echo.

call :port_open 8000
if not errorlevel 1 (
    echo [info] 127.0.0.1:8000 is already in use - reusing that MCP server.
) else (
    echo [1/2] Starting the MCP server ...
    start "ChaseLine - MCP server (:8000)" cmd /k ""%PY%" -m mcp_server.server"
    call :wait_port 8000 60
    if errorlevel 1 (
        echo [warn] The MCP server did not open port 8000 within 60 seconds.
        echo        Check its window for the error.
        set "FAILED=1"
    )
)
echo.

call :port_open 8080
if not errorlevel 1 (
    echo [info] 127.0.0.1:8080 is already in use - reusing that voice simulator.
) else (
    echo [2/2] Starting the voice simulator ...
    start "ChaseLine - voice simulator (:8080)" cmd /k ""%PY%" -m web_demo.app"
    call :wait_port 8080 60
    if errorlevel 1 (
        echo [warn] The voice simulator did not open port 8080 within 60 seconds.
        echo        Check its window for the error.
        set "FAILED=1"
    )
)
echo.

if defined FAILED (
    echo Something above needs attention - see the warnings and the two windows.
    echo.
    pause
    exit /b 1
)

echo Opening http://127.0.0.1:8080 in your browser.
echo Use Chrome or Edge - speech recognition is unavailable elsewhere.
start "" "http://127.0.0.1:8080"
echo.
echo Leave the two new windows running. Closing them stops the demo.
exit /b 0


:port_open
REM errorlevel 0 when something is listening on 127.0.0.1:%~1
powershell -NoProfile -Command "$c = New-Object Net.Sockets.TcpClient; try { $c.Connect([ipaddress]::Loopback, %~1); $c.Close(); exit 0 } catch { exit 1 }"
exit /b %errorlevel%


:wait_port
REM %1 = port, %2 = seconds to wait.  errorlevel 0 once it accepts connections.
powershell -NoProfile -Command "for ($i = 0; $i -lt %~2; $i++) { $c = New-Object Net.Sockets.TcpClient; try { $c.Connect([ipaddress]::Loopback, %~1); $c.Close(); exit 0 } catch { Start-Sleep -Seconds 1 } }; exit 1"
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
