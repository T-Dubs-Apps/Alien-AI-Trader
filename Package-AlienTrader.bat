@echo off
chcp 65001 >nul
echo.
echo +------------------------------------------+
echo |   Alien AI Trader -- Package for Sharing  |
echo +------------------------------------------+
echo.

:: Build timestamped zip name on Desktop
set DEST=%USERPROFILE%\Desktop\AlienAITrader-Share.zip

:: Remove old zip if it exists
if exist "%DEST%" del /f /q "%DEST%"

echo Building clean package (excluding .venv, keys.bat, __pycache__)...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$src  = Split-Path -Parent $MyInvocation.MyCommand.Path; " ^
  "$tmp  = Join-Path $env:TEMP 'AlienAITrader-Package'; " ^
  "if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }; " ^
  "New-Item -ItemType Directory -Path $tmp | Out-Null; " ^
  "$dest_inner = Join-Path $tmp 'Alien AI Trader disc'; " ^
  "robocopy $src $dest_inner /E /XD '.venv' '__pycache__' /XF 'keys.bat' '*.pyc' '*.log' /NP /NFL /NDL /NJH /NJS | Out-Null; " ^
  "Compress-Archive -Path $dest_inner -DestinationPath '%DEST%' -Force; " ^
  "Remove-Item $tmp -Recurse -Force; " ^
  "Write-Host 'Done! Zip saved to: %DEST%'"

echo.
echo Included in the zip:
echo   - QUICK SETUP.txt  (step-by-step instructions)
echo   - README.md        (full AI engine explanation)
echo   - All source files (no .venv or private keys)
echo.
echo Your brother will need to:
echo   1. Unzip the folder
echo   2. Double-click SETUP.bat      (installs Python deps)
echo   3. Fill in his own keys in keys.bat
echo   4. Double-click start-alien-ai-trader.bat
echo   5. Read QUICK SETUP.txt for full walkthrough
echo.
pause

:: Built by Troy Walker of T-Dub's Apps -- 2026-04-22
