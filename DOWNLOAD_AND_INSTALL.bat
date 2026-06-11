@echo off
chcp 65001 >nul 2>&1
title  Alien AI Trader - Download and Install
color 0B
echo.
echo  +==========================================================+
echo  ^|                                                          ^|
echo  ^|            ALIEN AI TRADER                            ^|
echo  ^|              Download and Install                        ^|
echo  ^|          Built by Troy Walker - T-Dub's Apps            ^|
echo  ^|                                                          ^|
echo  ^|  This will:                                              ^|
echo  ^|    1. Download the app from GitHub                       ^|
echo  ^|    2. Run the full installer automatically               ^|
echo  ^|    3. Walk you through getting your API keys             ^|
echo  ^|    4. Deploy to the cloud (optional)                     ^|
echo  ^|    5. Launch your dashboard                              ^|
echo  ^|                                                          ^|
echo  +==========================================================+
echo.

REM -- Check for git --------------------------------------------
where git >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Git is not installed on this machine.
    echo.
    echo  Git is needed to download the app from GitHub.
    echo  It is FREE and takes about 1 minute to install.
    echo.
    echo  Steps:
    echo    1. A browser window will open to the Git download page
    echo    2. Download and install Git  (keep all default settings)
    echo    3. Close this window and double-click this file again
    echo.
    pause
    start https://git-scm.com/download/win
    exit /b 1
)
echo  [OK] Git found.
echo.

REM -- Choose install location -----------------------------------
set "INSTALL_DIR=%USERPROFILE%\Desktop\Alien_AI_Trader"

echo  Install location: %INSTALL_DIR%
echo.

REM -- Clone or update the repo ----------------------------------
if exist "ONE_CLICK_INSTALL.bat" (
    echo  [OK] Alien AI Trader is already available in this folder.
    set "INSTALL_DIR=%CD%"
) else (
    if exist "%INSTALL_DIR%\ONE_CLICK_INSTALL.bat" (
        echo  [OK] Alien AI Trader already downloaded. Updating...
        cd /d "%INSTALL_DIR%"
        git pull origin main
        echo  [OK] Updated to latest version.
    ) else (
        echo  Downloading Alien AI Trader from GitHub...
        git clone https://github.com/T-Dubs-Apps/Alien-AI-Trader.git "%INSTALL_DIR%"
        if errorlevel 1 (
            echo  [ERROR] Download failed. Check your internet connection and try again.
            pause
            exit /b 1
        )
        echo  [OK] Download complete.
    )
)

echo.
echo  Launching installer...
echo.

cd /d "%INSTALL_DIR%"
call ONE_CLICK_INSTALL.bat
