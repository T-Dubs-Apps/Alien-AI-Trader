@echo off
chcp 65001 >nul 2>&1
title Alien AI Trader - Local Dev Server
color 0A

:: ─────────────────────────────────────────
::  Load API keys and trading settings from
::  keys.bat (your private, gitignored file).
::  If keys.bat is missing, run SETUP.bat first.
:: ─────────────────────────────────────────
if not exist "%~dp0keys.bat" (
    echo.
    echo  [ERROR] keys.bat not found.
    echo  Run SETUP.bat first to create it, then fill in your API keys.
    echo.
    pause
    exit /b 1
)
call "%~dp0keys.bat"

:: ─────────────────────────────────────────
::  Move to this folder
:: ─────────────────────────────────────────
cd /d "%~dp0"

:: ─────────────────────────────────────────
::  Warn if keys are still placeholders
:: ─────────────────────────────────────────
if "%ALPACA_KEY%"=="YOUR_ALPACA_KEY_HERE" (
    echo.
    echo  [WARNING] You have not filled in your API keys yet!
    echo  Open  keys.bat  in Notepad and replace:
    echo    YOUR_ALPACA_KEY_HERE
    echo    YOUR_ALPACA_SECRET_HERE
    echo    YOUR_ALPHA_VANTAGE_KEY_HERE
    echo    YOUR_PUSHBULLET_TOKEN_HERE
    echo.
    echo  The dashboard will still start but live data will not load.
    echo.
    pause
)

:: ─────────────────────────────────────────
::  Verify Python is available
:: ─────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [ERROR] Python not found in PATH.
    echo  Install Python from https://python.org and check "Add to PATH".
    echo.
    pause
    exit /b 1
)

echo [INFO] Python found: 
python --version

:: ─────────────────────────────────────────
::  Create venv if it doesn't exist
:: ─────────────────────────────────────────
if not exist ".venv\Scripts\python.exe" (
    echo [SETUP] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

:: ─────────────────────────────────────────
::  Activate and install dependencies
:: ─────────────────────────────────────────
echo [SETUP] Activating venv...
call .venv\Scripts\activate.bat

echo [SETUP] Installing dependencies (first run may take a minute)...
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] pip install failed. Check your internet connection.
    pause
    exit /b 1
)

:: ─────────────────────────────────────────
::  Open browser then start server
:: ─────────────────────────────────────────
echo.
echo ============================================
echo   Alien AI Trader running at:
echo   http://localhost:5000
echo   Press Ctrl+C to stop
echo ============================================
echo.

start "" "http://localhost:5000"
python dashboard.py

echo.
echo [SERVER STOPPED]
pause
