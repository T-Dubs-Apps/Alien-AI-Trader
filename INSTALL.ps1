# ============================================================
#  ALIEN AI TRADER — Windows Installer & Launcher
#  Built by Troy Walker of T-Dub's Apps — 2026
#  Run this as the VERY FIRST STEP on a new machine.
#  Right-click → "Run with PowerShell"
# ============================================================

$Host.UI.RawUI.WindowTitle = "Alien AI Trader — Installer"
$ErrorActionPreference = "Stop"

function Write-Header {
    Clear-Host
    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "  ║        ALIEN AI TRADER — WINDOWS INSTALLER          ║" -ForegroundColor Cyan
    Write-Host "  ║        Built by Troy Walker of T-Dub's Apps         ║" -ForegroundColor Cyan
    Write-Host "  ╚══════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Step { param($n, $total, $msg)
    Write-Host "  [$n/$total] $msg" -ForegroundColor Yellow
}
function Write-OK   { param($msg) Write-Host "  ✔  $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "  ⚠  $msg" -ForegroundColor Yellow }
function Write-Err  { param($msg) Write-Host "  ✖  $msg" -ForegroundColor Red }
function Write-Info { param($msg) Write-Host "  ℹ  $msg" -ForegroundColor Cyan }

Write-Header

# ── STEP 1: Check execution policy ──────────────────────────
Write-Step 1 7 "Checking PowerShell execution policy..."
$policy = Get-ExecutionPolicy -Scope CurrentUser
if ($policy -eq "Restricted" -or $policy -eq "AllSigned") {
    Write-Warn "Execution policy is '$policy'. Updating to RemoteSigned for this user..."
    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force
    Write-OK "Execution policy updated."
} else {
    Write-OK "Execution policy OK ($policy)."
}

# ── STEP 2: Check / Install Python ──────────────────────────
Write-Step 2 7 "Checking for Python 3.10+..."

$pythonOK = $false
$pythonCmd = $null

foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 10) {
                Write-OK "Found $ver (using '$cmd')"
                $pythonCmd = $cmd
                $pythonOK = $true
                break
            } else {
                Write-Warn "Found $ver but need 3.10+. Will install newer version."
            }
        }
    } catch { }
}

if (-not $pythonOK) {
    Write-Warn "Python 3.10+ not found. Attempting to install via winget..."

    # Try winget first (Windows 11 / updated Win10)
    $wingetAvail = $null
    try { $wingetAvail = Get-Command winget -ErrorAction Stop } catch { }

    if ($wingetAvail) {
        Write-Info "Installing Python 3.12 via winget..."
        winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
        # Refresh PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path","User")
        $pythonCmd = "python"
        Write-OK "Python installed via winget."
    } else {
        # Fallback: download installer directly
        Write-Info "winget not available. Downloading Python 3.12 installer..."
        $installer = "$env:TEMP\python-3.12-installer.exe"
        $url = "https://www.python.org/ftp/python/3.12.0/python-3.12.0-amd64.exe"
        Write-Info "Downloading from python.org..."
        Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing
        Write-Info "Running installer (please follow prompts — check 'Add Python to PATH')..."
        Start-Process -FilePath $installer -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_pip=1" -Wait
        Remove-Item $installer -Force -ErrorAction SilentlyContinue
        # Refresh PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path","User")
        $pythonCmd = "python"
        Write-OK "Python installed."
    }

    # Verify install succeeded
    try {
        $ver = & python --version 2>&1
        Write-OK "Verified: $ver"
    } catch {
        Write-Err "Python install failed or PATH not updated. Please install Python 3.10+ manually from https://python.org"
        Write-Info "Make sure to check 'Add Python to PATH' during installation."
        pause
        exit 1
    }
}

# ── STEP 3: Check / upgrade pip ─────────────────────────────
Write-Step 3 7 "Checking pip..."
try {
    & $pythonCmd -m pip --version | Out-Null
    Write-OK "pip is available. Upgrading to latest..."
    & $pythonCmd -m pip install --upgrade pip --quiet
    Write-OK "pip up to date."
} catch {
    Write-Warn "pip not found. Installing..."
    & $pythonCmd -m ensurepip --upgrade
    Write-OK "pip installed."
}

# ── STEP 4: Locate repo / script directory ──────────────────
Write-Step 4 7 "Locating Alien AI Trader directory..."
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir
Write-OK "Working directory: $scriptDir"

# ── STEP 5: Create / activate virtual environment ───────────
Write-Step 5 7 "Setting up virtual environment..."
$venvPath = Join-Path $scriptDir ".venv"

if (-not (Test-Path "$venvPath\Scripts\python.exe")) {
    Write-Info "Creating virtual environment..."
    & $pythonCmd -m venv $venvPath
    Write-OK "Virtual environment created at .venv"
} else {
    Write-OK "Virtual environment already exists."
}

$venvPython = "$venvPath\Scripts\python.exe"
$venvPip    = "$venvPath\Scripts\pip.exe"

# Activate for this session
& "$venvPath\Scripts\Activate.ps1" 2>$null
Write-OK "Virtual environment activated."

# ── STEP 6: Install requirements ────────────────────────────
Write-Step 6 7 "Installing Python requirements..."
$reqFile = Join-Path $scriptDir "requirements.txt"

if (Test-Path $reqFile) {
    Write-Info "Installing from requirements.txt..."
    & $venvPip install -r $reqFile --quiet
    Write-OK "All requirements installed."
} else {
    Write-Warn "requirements.txt not found. Installing core packages manually..."
    $packages = @(
        "flask", "flask-cors", "flask-socketio",
        "alpaca-trade-api", "alpha_vantage",
        "pushbullet.py", "twilio",
        "requests", "python-dotenv", "gunicorn",
        "eventlet"
    )
    foreach ($pkg in $packages) {
        Write-Info "Installing $pkg..."
        & $venvPip install $pkg --quiet
    }
    Write-OK "Core packages installed."
}

# ── STEP 7: Check for keys.bat ──────────────────────────────
Write-Step 7 7 "Checking for API keys configuration..."
$keysBat  = Join-Path $scriptDir "keys.bat"
$keysTemp = Join-Path $scriptDir "keys.bat.template"

if (-not (Test-Path $keysBat)) {
    Write-Warn "keys.bat not found."
    if (Test-Path $keysTemp) {
        Write-Info "Found keys.bat.template — copying..."
        Copy-Item $keysTemp $keysBat
        Write-Warn "You must edit keys.bat with your API keys before running the app."
        Write-Info "Or run: python setup_wizard.py (walks you through it step by step)"
    } else {
        Write-Info "Run setup_wizard.py to create your keys.bat automatically."
    }
} else {
    Write-OK "keys.bat found."
}

# ── DONE ────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ══════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  ✦  Installation Complete!" -ForegroundColor Green
Write-Host "  ══════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor White
Write-Host "    1. Double-click  RUN-SETUP-WIZARD.bat   (set up your API keys)" -ForegroundColor Cyan
Write-Host "    2. Double-click  start-alien-ai-trader.bat  (launch the app)" -ForegroundColor Cyan
Write-Host "    3. Open browser: http://localhost:5000" -ForegroundColor Cyan
Write-Host ""
Write-Host "  OR just double-click START.bat to do everything at once." -ForegroundColor Yellow
Write-Host ""

Read-Host "  Press ENTER to exit installer"
