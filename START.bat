@echo off
title Alien AI Trader — Launching...
color 0B
setlocal enabledelayedexpansion

echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║        ALIEN AI TRADER — QUICK LAUNCH               ║
echo  ║        Built by Troy Walker of T-Dub's Apps         ║
echo  ╚══════════════════════════════════════════════════════╝
echo.

REM ── Locate script directory ──────────────────────────────
cd /d "%~dp0"

REM ── Check Python ─────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found.
    echo.
    echo  Please run INSTALL.ps1 first:
    echo    Right-click INSTALL.ps1 → Run with PowerShell
    echo.
    pause
    exit /b 1
)

REM ── Activate virtual environment ─────────────────────────
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo  [OK] Virtual environment activated.
) else (
    echo  [WARN] No virtual environment found. Running INSTALL.ps1 now...
    powershell -ExecutionPolicy Bypass -File "INSTALL.ps1"
    if errorlevel 1 ( pause & exit /b 1 )
    call .venv\Scripts\activate.bat
)

REM ── Check keys.bat ───────────────────────────────────────
if not exist "keys.bat" (
    echo.
    echo  [WARN] keys.bat not found — launching Setup Wizard...
    echo.
    python setup_wizard.py
    if errorlevel 1 (
        echo  [ERROR] Setup wizard failed. Please run it manually.
        pause
        exit /b 1
    )
)

REM ── Load environment variables ───────────────────────────
if exist "keys.bat" (
    call keys.bat
    echo  [OK] Environment variables loaded.
)

REM ── Launch dashboard (web service + integrated trading engine) ──────────
echo.
echo  Starting Alien AI Trader...
start "Alien AI Trader" cmd /k "title Alien AI Trader ^& .venv\Scripts\activate.bat ^& call keys.bat ^& python dashboard.py"

REM ── Open browser ─────────────────────────────────────────
timeout /t 2 /nobreak >nul
echo  Opening dashboard in browser...
start http://localhost:5000

echo.
echo  ══════════════════════════════════════════════════════
echo   Alien AI Trader is RUNNING!
echo  ══════════════════════════════════════════════════════
echo.
echo   Dashboard:  http://localhost:5000
echo   The AI trading engine runs inside the same window.
echo.
echo   To stop: close the "Alien AI Trader" console window
echo  ══════════════════════════════════════════════════════
echo.
pause
