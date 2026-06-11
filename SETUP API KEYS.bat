@echo off
title Alien AI Trader - API Key Setup
color 0B
cd /d "%~dp0"

echo.
echo  +======================================================+
echo  ^|     ALIEN AI TRADER - API KEY SETUP WIZARD          ^|
echo  ^|     Walks you through getting every key, free       ^|
echo  +======================================================+
echo.

REM Prefer the app's own Python if already installed
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" setup_wizard.py
    goto :done
)

REM Otherwise any Python on this computer works (wizard needs nothing extra)
where py >nul 2>&1
if not errorlevel 1 (
    py setup_wizard.py
    goto :done
)
where python >nul 2>&1
if not errorlevel 1 (
    python setup_wizard.py
    goto :done
)

echo  [ERROR] Python was not found on this computer.
echo.
echo  Run LAUNCH.bat and choose [1] INSTALL first -
echo  it installs Python for you automatically.

:done
echo.
pause
