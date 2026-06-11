@echo off
title Alien AI Trader - Launching...
color 0B
setlocal enabledelayedexpansion

echo.
echo  +======================================================+
echo  ^|        ALIEN AI TRADER - QUICK LAUNCH               ^|
echo  ^|        Built by Troy Walker of T-Dub's Apps         ^|
echo  +======================================================+
echo.

REM -- Locate script directory ------------------------------
cd /d "%~dp0"

REM -- Activate virtual environment -------------------------
REM The app's own venv is all we need - no system Python required.
if exist ".venv\Scripts\python.exe" (
    call .venv\Scripts\activate.bat
    echo  [OK] Virtual environment activated.
) else (
    echo  [WARN] No virtual environment found. Running INSTALL.ps1 now...
    powershell -NoProfile -ExecutionPolicy Bypass -File "INSTALL.ps1"
    if errorlevel 1 ( pause & exit /b 1 )
    call .venv\Scripts\activate.bat
)

REM -- Check keys.bat ---------------------------------------
if not exist "keys.bat" (
    echo.
    echo  [WARN] keys.bat not found - launching Setup Wizard...
    echo.
    python setup_wizard.py
    if errorlevel 1 (
        echo  [ERROR] Setup wizard failed. Please run it manually.
        pause
        exit /b 1
    )
)

REM -- Load environment variables ---------------------------
if exist "keys.bat" (
    call "%~dp0keys.bat"
    echo  [OK] Environment variables loaded.
)

REM -- Launch dashboard (web service + integrated trading engine) ----------
REM RUN_APP.bat does activate + keys + python with no quoting tricks.
echo.
echo  Starting Alien AI Trader...
start "Alien AI Trader" /D "%~dp0" cmd /k "%~dp0RUN_APP.bat"

REM -- Open browser -----------------------------------------
timeout /t 2 /nobreak >nul
echo  Opening dashboard in browser...
start http://localhost:5000

echo.
echo  ======================================================
echo   Alien AI Trader is RUNNING!
echo  ======================================================
echo.
echo   Dashboard:  http://localhost:5000
echo   The AI trading engine runs inside the same window.
echo.
echo   To stop: close the "Alien AI Trader" console window
echo  ======================================================
echo.
pause
