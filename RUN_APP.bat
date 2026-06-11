@echo off
REM Inner runner used by START.bat / ONE_CLICK_INSTALL.bat.
REM Absolute paths only - no activate, no PATH games, no quoting tricks.
title Alien AI Trader
color 0B
cd /d "%~dp0"

if exist "%~dp0keys.bat" call "%~dp0keys.bat"

echo.
echo  Alien AI Trader is starting - keep this window open.
echo  Dashboard: http://localhost:5000
echo.

"%~dp0.venv\Scripts\python.exe" "%~dp0dashboard.py"

echo.
echo  [!] The app stopped. If there is an error above, read it -
echo      it explains what went wrong.
pause
