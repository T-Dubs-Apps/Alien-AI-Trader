@echo off
chcp 65001 >nul 2>&1
title Alien AI Trader - CD Installer
color 0B

echo.
echo  +================================================+
echo  |      ALIEN AI TRADER -- CD INSTALLER           |
echo  +================================================+
echo.
echo  This will copy Alien AI Trader to your computer
echo  and run first-time setup automatically.
echo.

:: ─────────────────────────────────────────
::  Default install location
:: ─────────────────────────────────────────
set "DEFAULT_DEST=%USERPROFILE%\Desktop\Alien AI Trader"
set "INSTALL_TO=%DEFAULT_DEST%"

echo  Default install location:
echo    %DEFAULT_DEST%
echo.
set /p "CUSTOM=Press Enter to use default, or type a new path: "
if not "%CUSTOM%"=="" set "INSTALL_TO=%CUSTOM%"

echo.
echo  Installing to: %INSTALL_TO%
echo.

:: ─────────────────────────────────────────
::  Create target directory
:: ─────────────────────────────────────────
if not exist "%INSTALL_TO%" (
    mkdir "%INSTALL_TO%"
    if errorlevel 1 (
        echo  [ERROR] Could not create folder: %INSTALL_TO%
        echo  Try running as Administrator or choose a different path.
        pause
        exit /b 1
    )
)

:: ─────────────────────────────────────────
::  Copy files from disc to hard drive
::  Robocopy is built into Windows 7+ / 11.
::  Exit codes 0-7 = success, 8+ = error.
:: ─────────────────────────────────────────
echo  [COPY] Copying files to hard drive...
robocopy "%~dp0" "%INSTALL_TO%" /E ^
    /XD .venv __pycache__ ^
    /XF keys.bat config.json autorun.inf *.pyc *.pyo *.db *.sqlite3 ^
    /NFL /NDL /NP /NJS /NJH

if errorlevel 8 (
    echo.
    echo  [ERROR] File copy failed. Check available disk space.
    pause
    exit /b 1
)
echo  [OK] Files copied.
echo.

:: ─────────────────────────────────────────
::  Launch SETUP.bat from the installed location
:: ─────────────────────────────────────────
if not exist "%INSTALL_TO%\SETUP.bat" (
    echo  [ERROR] SETUP.bat not found after copy. Disc may be incomplete.
    pause
    exit /b 1
)

echo  [LAUNCH] Starting setup from installed location...
echo.
start "" /wait "%INSTALL_TO%\SETUP.bat"

:: ─────────────────────────────────────────
::  Done
:: ─────────────────────────────────────────
echo.
echo  +========================================================+
echo  |  Installation complete!                                |
echo  |                                                        |
echo  |  Alien AI Trader is installed at:                      |
echo  |    %INSTALL_TO%
echo  |                                                        |
echo  |  A shortcut has been placed on your Desktop.           |
echo  |  Open  keys.bat  in Notepad and fill in your           |
echo  |  API keys before launching.                            |
echo  +========================================================+
echo.
pause
