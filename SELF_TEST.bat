@echo off
chcp 65001 >nul 2>&1
title 👽 Alien AI Trader — Self-Test
color 0B
cd /d "%~dp0"

echo.
echo  ╔══════════════════════════════════════════════════════════╗
echo  ║          👽  ALIEN AI TRADER — SELF-TEST               ║
echo  ║          Checking installation health...               ║
echo  ╚══════════════════════════════════════════════════════════╝
echo.

REM ── Activate virtual environment if present ──────────────────
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo  [WARN] No virtual environment found (.venv missing).
    echo  Using system Python — some package checks may fail.
    echo  Run LAUNCH.bat option [1] INSTALL to fix this.
    echo.
)

REM ── Load API keys if available ────────────────────────────────
if exist "keys.bat" (
    call keys.bat
)

REM ── Check Python is available ─────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found.
    echo  Run LAUNCH.bat option [1] INSTALL to install Python automatically.
    pause
    exit /b 1
)

REM ── Run self_test.py ──────────────────────────────────────────
echo  Running tests...
echo.
python self_test.py %*

REM ── Keep window open so results are visible ───────────────────
echo.
echo  ══════════════════════════════════════════════════════════
echo   Test run complete.
echo   To repair issues: run SELF_TEST.bat --repair
echo   To reinstall:     run LAUNCH.bat option [1] INSTALL
echo  ══════════════════════════════════════════════════════════
echo.
pause
