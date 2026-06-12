@echo off
REM Inner runner used by START.bat / ONE_CLICK_INSTALL.bat.
REM Absolute paths only - no activate, no PATH games, no quoting tricks.
title Alien AI Trader
color 0B
cd /d "%~dp0"

REM If the app is already running, do not crash trying to start a second
REM copy - just open the dashboard the user is looking for.
netstat -ano -p TCP | findstr "LISTENING" | findstr ":5000" >nul 2>&1
if not errorlevel 1 (
    echo.
    echo  Alien AI Trader is ALREADY RUNNING - no need to start it twice.
    echo  Opening your dashboard now...
    start http://localhost:5000
    echo.
    echo  To RESTART the app instead: close the other "Alien AI Trader"
    echo  window first, then double-click this again.
    echo.
    pause
    exit /b 0
)

if exist "%~dp0keys.bat" call "%~dp0keys.bat"

echo.
echo  Alien AI Trader is starting - keep this window open.
echo  Dashboard: http://localhost:5000
echo.

"%~dp0.venv\Scripts\python.exe" "%~dp0dashboard.py"

echo.
echo  [!] The app stopped. If there is an error above, read it -
echo      it explains what went wrong.
pause
