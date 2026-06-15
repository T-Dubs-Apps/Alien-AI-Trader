@echo off
REM Hidden server runner for Alien AI Trader.
REM Launched by "Alien AI Trader.vbs" with no visible window. Keeps the Python
REM server alive inside this hidden console. Do not double-click this directly --
REM use the "Alien AI Trader" desktop icon instead.
cd /d "%~dp0"

REM If the app is already listening on port 5000, do NOT start a second copy.
netstat -ano -p TCP | findstr "LISTENING" | findstr ":5000" >nul 2>&1
if not errorlevel 1 exit /b 0

REM Load the user's saved keys / settings, if present.
if exist "%~dp0keys.bat" call "%~dp0keys.bat"

REM Run the dashboard + integrated trading engine. Output is written to a log
REM file so the window can stay hidden while still recording any problem.
"%~dp0.venv\Scripts\python.exe" "%~dp0dashboard.py" >> "%~dp0app_log.txt" 2>&1
