@echo off
REM Waits for the Alien AI Trader server to be ready, then opens the dashboard.
REM Launched hidden by "Alien AI Trader.vbs". Polls up to ~30 seconds so the
REM browser never opens to a "can't connect" page on a slow cold start.
cd /d "%~dp0"

for /l %%i in (1,1,30) do (
    ping 127.0.0.1 -n 2 >nul
    netstat -ano -p TCP | findstr "LISTENING" | findstr ":5000" >nul 2>&1
    if not errorlevel 1 (
        start "" "http://localhost:5000"
        exit /b 0
    )
)

REM Fallback: open the browser anyway after the wait.
start "" "http://localhost:5000"
