@echo off
chcp 65001 >nul 2>&1
title 👽 Alien AI Trader — One-Click Install and Deploy
color 0B
cd /d "%~dp0"

echo.
echo  ╔══════════════════════════════════════════════════════════╗
echo  ║                                                          ║
echo  ║          👽  ALIEN AI TRADER                            ║
echo  ║              One-Click Install and Deploy               ║
echo  ║          Built by Troy Walker — T-Dub's Apps            ║
echo  ║                                                          ║
echo  ║  What this does (fully automated):                       ║
echo  ║    PHASE 1 — Install on this machine                     ║
echo  ║              Python, packages, API keys, shortcut        ║
echo  ║    PHASE 2 — Push latest code to GitHub                  ║
echo  ║              So Render always gets the newest version     ║
echo  ║    PHASE 3 — Deploy to Render (cloud)                    ║
echo  ║              Push your API keys and trigger redeploy     ║
echo  ║    PHASE 4 — Open dashboards                             ║
echo  ║              Local + cloud, both ready to trade          ║
echo  ║                                                          ║
echo  ╚══════════════════════════════════════════════════════════╝
echo.

REM ── Open animated splash screen ──────────────────────────────
if exist "splash\index.html" (
    start "" "splash\index.html"
    timeout /t 2 /nobreak >nul
)

REM ── Detect if already installed ──────────────────────────────
set "ALREADY_INSTALLED=0"
if exist ".venv\Scripts\python.exe" (
    if exist "keys.bat" (
        set "ALREADY_INSTALLED=1"
    )
)

if "%ALREADY_INSTALLED%"=="1" (
    echo  Previous installation detected.
    echo.
    echo    [1] Re-run full install  (updates packages + re-runs wizard)
    echo    [2] Deploy only          (skip local install, push keys to Render)
    echo    [3] Just launch the app  (skip install and deploy)
    echo.
    set /p "REINSTALL=  Enter 1, 2, or 3 (default: 2): "
    if "%REINSTALL%"=="1" goto :full_install
    if "%REINSTALL%"=="3" goto :launch_app
    goto :skip_local_install
)

REM ─────────────────────────────────────────────────────────────
:full_install
echo.
echo  ══════════════════════════════════════════════════════════
echo   PHASE 1 of 4 — Local Install
echo  ══════════════════════════════════════════════════════════
echo.
echo  Starting installer... follow the prompts.
echo  (The wizard will open each API service in your browser)
echo.
powershell -ExecutionPolicy Bypass -File "INSTALL.ps1"
if errorlevel 1 (
    echo.
    echo  [ERROR] Local installer failed. See details above.
    echo  Fix the issue and re-run this file.
    pause
    exit /b 1
)
echo.
echo  [OK] PHASE 1 complete.
goto :github_push

REM ─────────────────────────────────────────────────────────────
:skip_local_install
echo.
echo  [SKIP] Local install skipped (already installed).

REM ─────────────────────────────────────────────────────────────
:github_push
REM Load keys into this session so deploy_to_render.py can read them
if exist "keys.bat" (
    call keys.bat
) else (
    echo  [WARN] keys.bat not found. Run the setup wizard first.
    echo  Double-click RUN-SETUP-WIZARD.bat then re-run this file.
    pause
    exit /b 1
)

echo.
echo  ══════════════════════════════════════════════════════════
echo   PHASE 2 of 4 — GitHub Sync
echo  ══════════════════════════════════════════════════════════
echo.
echo  Pushing latest code to GitHub so Render gets the newest version...
echo  (Your private keys are NEVER pushed — they are gitignored)
echo.

where git >nul 2>&1
if errorlevel 1 (
    echo  [SKIP] Git not found on this machine.
    echo  Install Git from https://git-scm.com to enable auto-push.
    echo  Render will deploy the last commit already on GitHub.
    goto :render_deploy
)

git rev-parse --git-dir >nul 2>&1
if errorlevel 1 (
    echo  [SKIP] This folder is not a git repository.
    echo  Render will deploy from the existing GitHub repo.
    goto :render_deploy
)

REM Stage everything except private files
git add . -- ":!keys.bat" ":!.env" ":!install_config.json" ":!*.pyc" ":!.venv/" >nul 2>&1

REM Only commit if there are staged changes
git diff --cached --quiet >nul 2>&1
if not errorlevel 1 (
    echo  [INFO] No new changes to push. GitHub is already up to date.
    goto :render_deploy
)

for /f "tokens=*" %%d in ('powershell -Command "Get-Date -Format 'yyyy-MM-dd HH:mm'"') do set "TIMESTAMP=%%d"
git commit -m "Auto-deploy: %TIMESTAMP%"
if errorlevel 1 (
    echo  [WARN] Git commit failed. Continuing with deploy...
    goto :render_deploy
)

git push origin main
if errorlevel 1 (
    echo  [WARN] Git push failed. Common reasons:
    echo    - Not authenticated (run: git config --global credential.helper manager)
    echo    - No remote set    (run: git remote add origin [your-repo-url])
    echo  Render will still deploy from the last successful push.
) else (
    echo  [OK] Code pushed to GitHub successfully.
)

REM ─────────────────────────────────────────────────────────────
:render_deploy
echo.
echo  ══════════════════════════════════════════════════════════
echo   PHASE 3 of 4 — Render Cloud Deploy
echo  ══════════════════════════════════════════════════════════
echo.

if "%RENDER_API_KEY%"=="" (
    echo  [SKIP] RENDER_API_KEY is not set in keys.bat.
    echo.
    echo  To enable automatic Render deployment:
    echo    1. Log in to render.com
    echo    2. Click your profile icon  →  Account Settings
    echo    3. Click API Keys  →  Create API Key
    echo    4. Copy the key (starts with rnd_...)
    echo    5. Add this line to keys.bat:
    echo         set RENDER_API_KEY=rnd_xxxxxxxxxxxxxxxxxxxx
    echo    6. Re-run this file
    echo.
    echo  Or manually set env vars and redeploy in the Render dashboard.
    echo.
    goto :done
)

echo  Render API key found. Connecting to Render...
echo.

REM Run deploy_to_render.py using the venv python
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe deploy_to_render.py
) else if exist "deploy_to_render.py" (
    python deploy_to_render.py
) else (
    echo  [ERROR] deploy_to_render.py not found. Cannot auto-deploy to Render.
    echo  Check that your installation is complete.
    goto :done
)

REM ─────────────────────────────────────────────────────────────
:done
echo.
echo  ══════════════════════════════════════════════════════════
echo   PHASE 4 of 4 — Opening Dashboards
echo  ══════════════════════════════════════════════════════════
echo.

REM Launch local app if not already running
if exist ".venv\Scripts\python.exe" (
    echo  Starting local dashboard...
    start "Dashboard" cmd /k "title Alien AI Trader - Dashboard ^& cd /d "%~dp0" ^& call .venv\Scripts\activate.bat ^& call keys.bat ^& python dashboard.py"
    timeout /t 4 /nobreak >nul
    start "Worker" cmd /k "title Alien AI Trader - Worker ^& cd /d "%~dp0" ^& call .venv\Scripts\activate.bat ^& call keys.bat ^& python worker.py"
    timeout /t 2 /nobreak >nul
    echo  Opening browser...
    start http://localhost:5000
)

REM Open Render dashboard
if not "%RENDER_API_KEY%"=="" (
    timeout /t 1 /nobreak >nul
    start https://dashboard.render.com
)

echo.
echo  ╔══════════════════════════════════════════════════════════╗
echo  ║                                                          ║
echo  ║   ✦  All Done! Alien AI Trader is running.              ║
echo  ║                                                          ║
echo  ║   Local:  http://localhost:5000                          ║
echo  ║   Cloud:  alien-ai-trader-dashboard.onrender.com         ║
echo  ║                                                          ║
echo  ║   Tip: The cloud services take 3-5 min to rebuild.      ║
echo  ║   Tip: Start in Paper Trading mode (fake money) first!  ║
echo  ║                                                          ║
echo  ╚══════════════════════════════════════════════════════════╝
echo.
pause
goto :eof

REM ─────────────────────────────────────────────────────────────
:launch_app
if exist "START.bat" (
    call START.bat
) else (
    echo  [ERROR] START.bat not found. Run option 1 to install first.
    pause
)
goto :eof
