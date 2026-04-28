@echo off
title Alien AI Trader — Setup Wizard
color 0B

echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║       ALIEN AI TRADER — SETUP WIZARD               ║
echo  ║       Built by Troy Walker of T-Dub's Apps         ║
echo  ╚══════════════════════════════════════════════════════╝
echo.

REM ── Check Python is installed ─────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python is not installed or not in PATH.
    echo  Please install Python 3.10+ from https://python.org
    echo  Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

REM ── Activate venv if it exists ────────────────────────────
if exist ".venv\Scripts\activate.bat" (
    echo  Activating virtual environment...
    call .venv\Scripts\activate.bat
) else (
    echo  No virtual environment found. Creating one now...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    echo  Installing requirements...
    pip install -r requirements.txt --quiet
)

REM ── Run the wizard ────────────────────────────────────────
echo  Launching Setup Wizard...
echo.
python setup_wizard.py

echo.
pause
