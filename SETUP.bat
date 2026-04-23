@echo off
chcp 65001 >nul 2>&1
title Alien AI Trader - First Time Setup
color 0B

echo.
echo  +================================================+
echo  |      ALIEN AI TRADER -- FIRST-TIME SETUP       |
echo  +================================================+
echo.

cd /d "%~dp0"

:: ─────────────────────────────────────────
::  Step 1: Check Python
:: ─────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found.
    echo.
    echo  Install Python 3.10 or newer from https://python.org
    echo  During install, CHECK the box "Add Python to PATH".
    echo.
    pause
    exit /b 1
)
echo  [OK] Python found:
python --version

:: ─────────────────────────────────────────
::  Step 2: Create keys.bat from template
:: ─────────────────────────────────────────
if not exist "keys.bat" (
    if exist "keys.bat.template" (
        copy "keys.bat.template" "keys.bat" >nul
        echo  [SETUP] Created keys.bat from template.
    ) else (
        echo  [WARNING] keys.bat.template missing. Skipping.
    )
) else (
    echo  [OK] keys.bat already exists.
)

:: ─────────────────────────────────────────
::  Step 3: Create virtual environment
:: ─────────────────────────────────────────
if not exist ".venv\Scripts\python.exe" (
    echo  [SETUP] Creating Python virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo  [ERROR] Could not create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo  [OK] Virtual environment already exists.
)

:: ─────────────────────────────────────────
::  Step 4: Install dependencies
:: ─────────────────────────────────────────
echo  [SETUP] Installing dependencies (this may take 1-2 minutes)...
call .venv\Scripts\activate.bat
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo  [ERROR] pip install failed. Check your internet connection.
    pause
    exit /b 1
)
echo  [OK] Dependencies installed.

:: ─────────────────────────────────────────
::  Step 5: Create Desktop shortcut
:: ─────────────────────────────────────────
set "SHORTCUT=%USERPROFILE%\Desktop\Alien AI Trader.lnk"
set "TARGET=%~dp0start-alien-ai-trader.bat"
powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath = '%TARGET%'; $s.WorkingDirectory = '%~dp0'; $s.Description = 'Start Alien AI Trader'; $s.Save()"

if exist "%SHORTCUT%" (
    echo  [OK] Desktop shortcut created: "Alien AI Trader"
) else (
    echo  [INFO] Shortcut could not be created. Run start-alien-ai-trader.bat directly.
)

:: ─────────────────────────────────────────
::  Done
:: ─────────────────────────────────────────
echo.
echo  +========================================================+
echo  |  Setup complete! Here is what to do next:              |
echo  |                                                        |
echo  |  1. Open  keys.bat  in Notepad                         |
echo  |  2. Replace YOUR_ALPACA_KEY_HERE etc. with             |
echo  |     your real API keys (see comments inside)           |
echo  |  3. Save keys.bat, then double-click                   |
echo  |     start-alien-ai-trader.bat  (or the shortcut)       |
echo  |                                                        |
echo  |  For real-money trading, read the instructions         |
echo  |  inside keys.bat before changing TRADING_MODE.         |
echo  +========================================================+
echo.
pause
