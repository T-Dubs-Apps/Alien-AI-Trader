@echo off
chcp 65001 >nul 2>&1
title Alien AI Trader — Installer
color 0B
cd /d "%~dp0"

echo.
echo  ╔══════════════════════════════════════════════════════════╗
echo  ║                                                          ║
echo  ║          👽  ALIEN AI TRADER  👽                         ║
echo  ║          AI-Powered Stock Trading                        ║
echo  ║          Built by Troy Walker — T-Dub's Apps            ║
echo  ║                                                          ║
echo  ╚══════════════════════════════════════════════════════════╝
echo.

REM ── Open the animated splash screen in the default browser ────
echo  Opening launch screen...
if exist "splash\index.html" (
    start "" "splash\index.html"
    timeout /t 2 /nobreak >nul
) else (
    echo  [INFO] Splash screen not found — continuing with console installer.
)

REM ── Show menu ─────────────────────────────────────────────────
echo.
echo  What would you like to do?
echo.
echo    [1] INSTALL — Copy to your PC and run full setup
echo    [2] RUN NOW — I already installed, just launch the app
echo    [3] SETUP KEYS — Re-run the API key wizard
echo    [4] OPEN README — Read the full documentation
echo    [5] EXIT
echo.
set /p "CHOICE=  Enter 1-5: "

if "%CHOICE%"=="1" goto :INSTALL
if "%CHOICE%"=="2" goto :RUN_NOW
if "%CHOICE%"=="3" goto :SETUP_KEYS
if "%CHOICE%"=="4" goto :OPEN_README
if "%CHOICE%"=="5" goto :END

echo  [ERROR] Invalid choice. Please run again and enter 1-5.
pause
goto :END

REM ─────────────────────────────────────────────────────────────
:INSTALL
echo.
echo  Starting installer...
echo  (This may take a few minutes — installing Python packages)
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "INSTALL.ps1"
if errorlevel 1 (
    echo.
    echo  [ERROR] The installer did not finish. Read any message above,
    echo          then try again or run INSTALL.ps1 directly:
    echo          Right-click INSTALL.ps1 - "Run with PowerShell"
)
goto :END

REM ─────────────────────────────────────────────────────────────
:RUN_NOW
echo.
if exist "START.bat" (
    call START.bat
) else (
    echo  [ERROR] START.bat not found. Please run option 1 to install first.
    pause
)
goto :END

REM ─────────────────────────────────────────────────────────────
:SETUP_KEYS
echo.
if exist ".venv\Scripts\python.exe" (
    call .venv\Scripts\activate.bat
    python setup_wizard.py
) else (
    echo  [ERROR] No virtual environment found. Please run option 1 first.
    pause
)
goto :END

REM ─────────────────────────────────────────────────────────────
:OPEN_README
echo.
if exist "README.md" (
    start notepad "README.md"
) else (
    echo  README.md not found.
)
goto :END

REM ─────────────────────────────────────────────────────────────
:END
echo.
echo  ══════════════════════════════════════════════════════════
echo   Thank you for choosing Alien AI Trader!
echo   Dashboard: http://localhost:5000
echo  ══════════════════════════════════════════════════════════
echo.
pause
