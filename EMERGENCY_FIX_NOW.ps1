$ErrorActionPreference = 'Stop'

Write-Host ""
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host " Alien AI Trader Emergency Recovery" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""

Set-Location $PSScriptRoot

if (Test-Path ".venv\Scripts\Activate.ps1") {
    & ".venv\Scripts\Activate.ps1"
}

# Prompt in terminal so secrets do not pass through chat.
$licenseSecret = Read-Host "Enter LICENSE_SECRET (input hidden by terminal history if your shell supports it)"
$renderApiKey  = Read-Host "Enter RENDER_API_KEY (or press Enter to skip redeploy)"
$ownerEmail    = Read-Host "Enter YOUR email"
$broEmail      = Read-Host "Enter BROTHER email"

if ([string]::IsNullOrWhiteSpace($licenseSecret)) {
    throw "LICENSE_SECRET is required."
}
if ([string]::IsNullOrWhiteSpace($ownerEmail) -or [string]::IsNullOrWhiteSpace($broEmail)) {
    throw "Both emails are required."
}

$env:LICENSE_SECRET = $licenseSecret
if (-not [string]::IsNullOrWhiteSpace($renderApiKey)) {
    $env:RENDER_API_KEY = $renderApiKey
}

Write-Host ""
Write-Host "[1/6] Optional Render redeploy" -ForegroundColor Yellow
if (-not [string]::IsNullOrWhiteSpace($renderApiKey)) {
    python deploy_to_render.py
} else {
    Write-Host "Skipped redeploy (no RENDER_API_KEY supplied)." -ForegroundColor DarkYellow
}

Write-Host ""
Write-Host "[2/6] Debug brother Stripe/license status" -ForegroundColor Yellow
python grant.py debug --email $broEmail

Write-Host ""
Write-Host "[3/6] Ensure brother annual license active" -ForegroundColor Yellow
python grant.py grant --email $broEmail --tier annual
python grant.py status --email $broEmail

Write-Host ""
Write-Host "[4/6] Ensure owner license active (no paid sub needed)" -ForegroundColor Yellow
python grant.py grant --email $ownerEmail --tier pro_annual
python grant.py status --email $ownerEmail

Write-Host ""
Write-Host "[5/6] Send update notice to both emails" -ForegroundColor Yellow
python update_agent.py run --version 2026.07.07 --title "Critical license and engine fix" --message "Licensing and engine reliability patch has been applied. Please accept this update." --update-url "https://github.com/T-Dubs-Apps/Alien-AI-Trader" --emails "$ownerEmail,$broEmail"

Write-Host ""
Write-Host "[6/6] Final checks" -ForegroundColor Yellow
python grant.py status --email $broEmail
python grant.py status --email $ownerEmail

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "If engine still shows offline, open each deployment and check /api/engine/diag after login." -ForegroundColor Green
Write-Host ""
