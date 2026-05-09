# ============================================================
#  ALIEN AI TRADER — Full Windows Installer v2.0
#  Built by Troy Walker of T-Dub's Apps — 2026
#
#  Supports: Windows 10 / 11 (any edition)
#  Run:  Right-click → "Run with PowerShell"
#        OR launched automatically by LAUNCH.bat / autorun
#
#  What this installer does (in order):
#    1. Fixes execution policy so PowerShell scripts can run
#    2. Checks Windows version (10+)
#    3. Installs Python 3.12 if missing (via winget or python.org)
#    4. Asks WHERE you want Alien AI Trader installed
#         Default: C:\Users\[You]\Desktop\Alien_AI_Trader
#    5. Copies all files to that location
#    6. Creates a Python virtual environment there
#    7. Installs all Python packages (Flask, Alpaca, Pandas, etc.)
#    8. Generates the alien icon (.ico) using Python + Pillow
#    9. Runs the interactive API key setup wizard
#         (opens each registration site, explains each service,
#          collects your keys, writes keys.bat automatically)
#   10. Creates a Desktop shortcut  →  double-click to launch
#   11. Optionally enables Cloud Sync (per-user, opt-in)
#   12. Launches the app and opens your browser
# ============================================================

$Host.UI.RawUI.WindowTitle = "Alien AI Trader — Installer v2.0"
$ErrorActionPreference = "Continue"   # Don't abort on non-fatal errors

# ── Helpers ─────────────────────────────────────────────────────────────────
function Write-Header {
    Clear-Host
    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "  ║                                                          ║" -ForegroundColor Cyan
    Write-Host "  ║          👽  ALIEN AI TRADER  — INSTALLER v2.0          ║" -ForegroundColor Cyan
    Write-Host "  ║          AI-Powered Stock Trading for Windows            ║" -ForegroundColor Cyan
    Write-Host "  ║          Built by Troy Walker · T-Dub's Apps · 2026     ║" -ForegroundColor Cyan
    Write-Host "  ║                                                          ║" -ForegroundColor Cyan
    Write-Host "  ╚══════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Section { param($title)
    Write-Host ""
    Write-Host "  ──────────────────────────────────────────────────────────" -ForegroundColor DarkCyan
    Write-Host "  $title" -ForegroundColor Yellow
    Write-Host "  ──────────────────────────────────────────────────────────" -ForegroundColor DarkCyan
}

function Write-Step  { param($n,$total,$msg) Write-Host "  [$n/$total] $msg" -ForegroundColor Yellow }
function Write-OK    { param($msg) Write-Host "  ✔  $msg" -ForegroundColor Green }
function Write-Warn  { param($msg) Write-Host "  ⚠  $msg" -ForegroundColor Yellow }
function Write-Err   { param($msg) Write-Host "  ✖  $msg" -ForegroundColor Red }
function Write-Info  { param($msg) Write-Host "  ℹ  $msg" -ForegroundColor Cyan }
function Write-Teach { param($msg) Write-Host "  📖 $msg" -ForegroundColor Magenta }

function Pause-Continue { param($msg = "  Press ENTER to continue...")
    Write-Host ""
    Read-Host $msg | Out-Null
}

Write-Header

# ── STEP 0: Windows version check ────────────────────────────────────────────
Write-Section "STEP 0 — Checking Windows Version"
Write-Teach "Alien AI Trader requires Windows 10 or higher."
Write-Teach "Older versions lack the PowerShell features needed for automated install."

$winVer = [System.Environment]::OSVersion.Version
if ($winVer.Major -lt 10) {
    Write-Err "Windows $($winVer.Major) detected — Windows 10 or higher is required."
    Write-Info "Please upgrade your operating system before installing."
    Pause-Continue "Press ENTER to exit..."
    exit 1
}
Write-OK "Windows $($winVer.Major).$($winVer.Minor) — compatible!"

# ── STEP 1: Execution policy ──────────────────────────────────────────────────
Write-Section "STEP 1 — PowerShell Execution Policy"
Write-Teach "Windows blocks unsigned scripts by default for security."
Write-Teach "We set 'RemoteSigned' for your user — this allows local scripts"
Write-Teach "to run while still blocking unsigned scripts from the internet."

$policy = Get-ExecutionPolicy -Scope CurrentUser
if ($policy -in @("Restricted", "AllSigned")) {
    Write-Warn "Policy is '$policy'. Updating to RemoteSigned..."
    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force
    Write-OK "Execution policy updated to RemoteSigned."
} else {
    Write-OK "Policy OK: $policy"
}

# ── STEP 2: Python check / install ───────────────────────────────────────────
Write-Section "STEP 2 — Python 3.10+"
Write-Teach "Alien AI Trader is written in Python — a free, open-source language."
Write-Teach "We need Python 3.10+ for modern syntax features and library compatibility."
Write-Teach "Python will be installed only for your user account (not system-wide)."

$pythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python (\d+)\.(\d+)") {
            if ([int]$Matches[1] -ge 3 -and [int]$Matches[2] -ge 10) {
                Write-OK "Found $ver  (command: '$cmd')"
                $pythonCmd = $cmd
                break
            } else {
                Write-Warn "Found $ver but need 3.10+. Looking for a newer version..."
            }
        }
    } catch { }
}

if (-not $pythonCmd) {
    Write-Warn "Python 3.10+ not found. Installing Python 3.12..."

    $wingetOK = $null
    try { $wingetOK = Get-Command winget -ErrorAction Stop } catch { }

    if ($wingetOK) {
        Write-Info "Using winget (built-in package manager on Win10/11)..."
        winget install -e --id Python.Python.3.12 --silent `
              --accept-package-agreements --accept-source-agreements
    } else {
        Write-Info "winget not available. Downloading Python 3.12 from python.org..."
        $tmp = "$env:TEMP\python312.exe"
        Invoke-WebRequest `
            -Uri "https://www.python.org/ftp/python/3.12.0/python-3.12.0-amd64.exe" `
            -OutFile $tmp -UseBasicParsing
        Write-Info "Running installer (silent, adds Python to PATH)..."
        Start-Process $tmp -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_pip=1" -Wait
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    }

    # Refresh PATH so new python is visible
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path","User")
    $pythonCmd = "python"
    try { Write-OK "Verified: $(& python --version 2>&1)" } catch {
        Write-Err "Python install may have failed. Please install Python 3.10+ from https://python.org"
        Write-Info "Make sure to check 'Add Python to PATH' during installation."
        Pause-Continue "Press ENTER to exit..."
        exit 1
    }
}

# ── STEP 3: Choose install location ──────────────────────────────────────────
Write-Section "STEP 3 — Choose Install Location"
Write-Teach "You can install Alien AI Trader anywhere on your PC."
Write-Teach "The default location puts it right on your Desktop for easy access."
Write-Teach "All files, libraries, and settings will be stored in this one folder."
Write-Teach "Tip: Avoid paths with spaces if possible, e.g. use Alien_AI_Trader."
Write-Host ""

$defaultPath = "$env:USERPROFILE\Desktop\Alien_AI_Trader"

Write-Host "  Default install path:" -ForegroundColor White
Write-Host "    $defaultPath" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Other common choices:" -ForegroundColor DarkGray
Write-Host "    C:\Apps\Alien_AI_Trader" -ForegroundColor DarkGray
Write-Host "    C:\Users\$env:USERNAME\Documents\Alien_AI_Trader" -ForegroundColor DarkGray
Write-Host ""

$customPath = Read-Host "  Press ENTER for default, or type your preferred path"
$installPath = if ($customPath.Trim()) { $customPath.Trim() } else { $defaultPath }

Write-Host ""
Write-OK "Installing to: $installPath"

# Create the directory
if (-not (Test-Path $installPath)) {
    try {
        New-Item -ItemType Directory -Path $installPath -Force | Out-Null
        Write-OK "Directory created."
    } catch {
        Write-Err "Could not create: $installPath"
        Write-Info "Try running as Administrator, or choose a different path."
        Pause-Continue; exit 1
    }
} else {
    Write-Info "Directory already exists — files will be updated in place."
}

# ── STEP 4: Copy files ───────────────────────────────────────────────────────
Write-Section "STEP 4 — Copying Files"
Write-Teach "Copying all Alien AI Trader files to your install location."
Write-Teach "Skipping: .venv (will be rebuilt), keys.bat (your private keys),"
Write-Teach "          __pycache__ (compiled bytecode, auto-regenerated)."

$sourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if ($sourceDir -ne $installPath) {
    $robocopyArgs = @(
        $sourceDir, $installPath,
        "/E",
        "/XD", ".venv", "__pycache__", ".git", ".claude",
        "/XF", "keys.bat", "*.pyc", "*.pyo", "*.db", "*.sqlite3",
        "/NFL", "/NDL", "/NP", "/NJS", "/NJH"
    )
    $rc = (Start-Process "robocopy" -ArgumentList $robocopyArgs -Wait -PassThru).ExitCode
    if ($rc -ge 8) {
        Write-Err "File copy encountered errors (robocopy exit: $rc)."
        Write-Warn "Continuing anyway — some files may be missing."
    } else {
        Write-OK "Files copied successfully."
    }
} else {
    Write-Info "Source and destination are the same — no copy needed."
}

Set-Location $installPath

# ── STEP 5: Virtual environment ──────────────────────────────────────────────
Write-Section "STEP 5 — Python Virtual Environment"
Write-Teach "A virtual environment is an isolated Python workspace for this app."
Write-Teach "It keeps Alien AI Trader's libraries separate from other Python programs."
Write-Teach "This prevents version conflicts and makes the app self-contained."

$venvPath   = Join-Path $installPath ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$venvPip    = Join-Path $venvPath "Scripts\pip.exe"

if (-not (Test-Path $venvPython)) {
    Write-Info "Creating virtual environment at .venv ..."
    & $pythonCmd -m venv $venvPath
    Write-OK "Virtual environment created."
} else {
    Write-OK "Virtual environment already exists — reusing."
}

try { & "$venvPath\Scripts\Activate.ps1" 2>$null } catch { }

# ── STEP 6: Install requirements ─────────────────────────────────────────────
Write-Section "STEP 6 — Installing Python Packages"
Write-Teach "Installing all required libraries from requirements-local.txt."
Write-Teach ""
Write-Teach "Key packages and what they do:"
Write-Teach "  flask          — The web server that powers the dashboard UI"
Write-Teach "  flask-socketio — Real-time WebSocket push (live price updates)"
Write-Teach "  alpaca-trade-api — Connects to Alpaca to execute trades"
Write-Teach "  alpha_vantage  — Downloads RSI, SMA, and price bar data"
Write-Teach "  pandas         — Calculates technical indicators (RSI-14, SMA crossover)"
Write-Teach "  Pillow         — Generates the alien icon for your desktop shortcut"
Write-Teach "  twilio         — Sends SMS/phone call alerts to your phone"
Write-Teach "  gevent         — Async engine for the WebSocket server"
Write-Teach ""
Write-Teach "This may take 2–5 minutes on first install."

$reqFile = Join-Path $installPath "requirements-local.txt"
if (Test-Path $reqFile) {
    Write-Info "Installing from requirements-local.txt..."
    & $venvPip install -r $reqFile --quiet
    Write-OK "All packages installed."
} else {
    Write-Warn "requirements-local.txt not found — installing core packages manually..."
    $pkgs = @("flask","flask-cors","flask-socketio","alpaca-trade-api",
              "alpha_vantage","pandas","Pillow","requests","pushbullet.py",
              "twilio","gevent","gunicorn","stripe","sendgrid")
    foreach ($pkg in $pkgs) {
        Write-Info "  Installing $pkg..."
        & $venvPip install $pkg --quiet
    }
    Write-OK "Core packages installed."
}

# Upgrade pip silently
& $venvPip install --upgrade pip --quiet 2>$null

# ── STEP 7: Generate icon ────────────────────────────────────────────────────
Write-Section "STEP 7 — Generating Alien Icon"
Write-Teach "Creating the alien face icon for your Desktop shortcut."
Write-Teach "To use your own custom image: replace installer\alien_icon.ico"
Write-Teach "with any 256x256 ICO file (Windows icon editors can convert PNGs)."

$iconScript = Join-Path $installPath "make_icon.py"
$iconOut    = Join-Path $installPath "installer\alien_icon.ico"

if (Test-Path $iconScript) {
    & $venvPython $iconScript
    if (Test-Path $iconOut) {
        Write-OK "Icon generated: installer\alien_icon.ico"
    } else {
        Write-Warn "Icon generation failed — shortcut will use default Windows icon."
    }
} else {
    Write-Warn "make_icon.py not found — skipping icon generation."
}

# ── STEP 8: API Keys Setup Wizard ────────────────────────────────────────────
Write-Section "STEP 8 — API Keys Setup Wizard"
Write-Teach "Alien AI Trader needs API keys to connect to financial services."
Write-Teach "The wizard will open each registration page in your browser,"
Write-Teach "explain exactly what each service does and what to copy, then"
Write-Teach "write your keys.bat file automatically — no manual editing needed."
Write-Teach ""
Write-Teach "Services you'll register for:"
Write-Teach "  📈 Alpaca Markets — Stock trading execution + real-time prices"
Write-Teach "       Paper trading is INSTANT and FREE (fake money for testing)."
Write-Teach "       Live trading requires identity verification — NOT guaranteed;"
Write-Teach "       Alpaca approves accounts at their sole discretion."
Write-Teach "  📊 Alpha Vantage — RSI / SMA / price bar data (free)"
Write-Teach "  🔔 Pushover       — Push notifications to your phone"
Write-Teach "  📱 Twilio         — SMS text + phone call alerts (optional)"
Write-Teach "  🔗 Pushbullet     — Multi-device notification sync (optional)"
Write-Teach ""

$keysFile = Join-Path $installPath "keys.bat"
$skipWizard = $false
if (Test-Path $keysFile) {
    Write-OK "keys.bat already exists."
    $rerun = Read-Host "  Re-run the wizard to update your keys? (y/N)"
    if ($rerun -notin @("y","Y","yes","YES")) {
        Write-Info "Keeping existing keys.bat."
        $skipWizard = $true
    }
}

if (-not $skipWizard) {
    $wizardScript = Join-Path $installPath "setup_wizard.py"
    if (Test-Path $wizardScript) {
        Write-Info "Launching wizard..."
        & $venvPython $wizardScript
        if (Test-Path $keysFile) {
            Write-OK "keys.bat created successfully."
        } else {
            Write-Warn "Wizard completed but keys.bat was not found."
            Write-Info "You can run setup_wizard.py manually at any time."
        }
    } else {
        Write-Warn "setup_wizard.py not found. Create keys.bat manually."
    }
}

# ── STEP 9: Desktop shortcut ────────────────────────────────────────────────
Write-Section "STEP 9 — Desktop Shortcut"
Write-Teach "Creating a Desktop shortcut so you can launch Alien AI Trader"
Write-Teach "with one double-click — no need to find the folder each time."

$iconFile        = if (Test-Path $iconOut) { $iconOut } else { "" }
$oneClickBat     = Join-Path $installPath "ONE_CLICK_INSTALL.bat"
$startBat        = Join-Path $installPath "START.bat"
$ws = New-Object -ComObject WScript.Shell

# Shortcut 1 — Daily launcher: "Alien AI Trader"
try {
    $sc = $ws.CreateShortcut("$env:USERPROFILE\Desktop\Alien AI Trader.lnk")
    $sc.TargetPath       = $startBat
    $sc.WorkingDirectory = $installPath
    $sc.Description      = "Alien AI Trader — Launch the app"
    if ($iconFile) { $sc.IconLocation = $iconFile }
    $sc.Save()
    Write-OK "Desktop shortcut created: 'Alien AI Trader' (daily launch)"
} catch {
    Write-Warn "Could not create launch shortcut: $_"
}

# Shortcut 2 — Setup & Deploy: "Alien AI Trader — Setup"
if (Test-Path $oneClickBat) {
    try {
        $sc2 = $ws.CreateShortcut("$env:USERPROFILE\Desktop\Alien AI Trader — Setup.lnk")
        $sc2.TargetPath       = $oneClickBat
        $sc2.WorkingDirectory = $installPath
        $sc2.Description      = "Alien AI Trader — Full install + GitHub push + Render deploy"
        if ($iconFile) { $sc2.IconLocation = $iconFile }
        $sc2.Save()
        Write-OK "Desktop shortcut created: 'Alien AI Trader — Setup' (install + deploy)"
    } catch {
        Write-Warn "Could not create setup shortcut: $_"
    }
}

# ── STEP 10: Cloud Sync option ───────────────────────────────────────────────
Write-Section "STEP 10 — Cloud Sync (Optional)"
Write-Teach "Alien AI Trader can optionally sync your settings and trade logs"
Write-Teach "to your personal cloud account. This feature is:"
Write-Teach "  • OFF by default — nothing is uploaded unless YOU enable it"
Write-Teach "  • Per-user — your data is never shared with anyone"
Write-Teach "  • Optional — the app works perfectly fine without it"
Write-Teach "  • Accessible from any device once enabled in the Settings tab"
Write-Host ""

$cloudChoice = Read-Host "  Enable Cloud Sync for your account? (y/N)"
$cloudEnabled = $cloudChoice -in @("y","Y","yes","YES")

if ($cloudEnabled) {
    Write-Info "Cloud Sync will be enabled. Configure your account in the Settings tab."
    $cloudEnvLine = "`nset CLOUD_SYNC_ENABLED=true"
} else {
    Write-Info "Cloud Sync is OFF. You can enable it later in the Settings tab."
    $cloudEnvLine = "`nset CLOUD_SYNC_ENABLED=false"
}

# Append cloud sync setting to keys.bat if it exists
if (Test-Path $keysFile) {
    $current = Get-Content $keysFile -Raw
    if ($current -notmatch "CLOUD_SYNC_ENABLED") {
        Add-Content -Path $keysFile -Value $cloudEnvLine
    }
}

# ── STEP 11: Write a machine-specific config ─────────────────────────────────
Write-Section "STEP 11 — Saving Install Configuration"
Write-Teach "Writing install_config.json so the app knows exactly where it lives"
Write-Teach "on this specific machine. Each device gets its own config."

$configPath = Join-Path $installPath "install_config.json"
$config = @{
    install_path   = $installPath
    installed_on   = (Get-Date -Format "yyyy-MM-dd HH:mm")
    machine_name   = $env:COMPUTERNAME
    user           = $env:USERNAME
    python_cmd     = $venvPython
    cloud_sync     = $cloudEnabled
    version        = "2.0"
} | ConvertTo-Json -Depth 3

Set-Content -Path $configPath -Value $config -Encoding UTF8
Write-OK "Config saved: install_config.json"

# ── DONE ─────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ╔══════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "  ║                                                          ║" -ForegroundColor Green
Write-Host "  ║   ✦  Installation Complete!  👽                         ║" -ForegroundColor Green
Write-Host "  ║                                                          ║" -ForegroundColor Green
Write-Host "  ╚══════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  Installed to: $installPath" -ForegroundColor Cyan
Write-Host ""
Write-Host "  How to launch Alien AI Trader:" -ForegroundColor White
Write-Host "    • Double-click 'Alien AI Trader' on your Desktop" -ForegroundColor Green
Write-Host "    • OR double-click START.bat in: $installPath" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Your dashboard will open at: http://localhost:5000" -ForegroundColor Cyan
Write-Host "  Render cloud dashboard:      https://alien-ai-trader-dashboard.onrender.com" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Quick tips:" -ForegroundColor Yellow
Write-Host "    • Start with Paper Trading (fake money) — flip to Live when ready" -ForegroundColor White
Write-Host "    • Set Starting Capital $ in the Trade tab to enable compound mode" -ForegroundColor White
Write-Host "    • Turn on 'Scan Entire Market' to let the AI hunt all US stocks" -ForegroundColor White
Write-Host "    • Read README.md for the full AI trading engine explanation" -ForegroundColor White
Write-Host ""

$launch = Read-Host "  Launch Alien AI Trader now? (Y/n)"
if ($launch -notin @("n","N","no","NO")) {
    Write-Info "Launching..."
    Start-Process -FilePath $startBat -WorkingDirectory $installPath
    Start-Sleep -Seconds 4
    Start-Process "http://localhost:5000"
    Write-OK "App launched! Your browser will open in a moment."
}

Write-Host ""
Write-Host "  Good luck trading, Commander! 🛸" -ForegroundColor Cyan
Write-Host ""
Read-Host "  Press ENTER to close installer"
