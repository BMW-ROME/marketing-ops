# lead-gen/setup.ps1
# One-time local bootstrap for the LeadGen pipeline on Windows/PowerShell.
# Run from repo root: .\lead-gen\setup.ps1

$ErrorActionPreference = "Stop"
$leadGenDir = Join-Path $PSScriptRoot ""
Set-Location $leadGenDir

Write-Host "== Marketing-Ops LeadGen: local setup ==" -ForegroundColor Cyan

if (-not (Test-Path ".\.venv")) {
    Write-Host "Creating virtual environment (.venv)..." -ForegroundColor Yellow
    python -m venv .venv
} else {
    Write-Host "Virtual environment already exists, skipping creation." -ForegroundColor DarkGray
}

Write-Host "Activating virtual environment..." -ForegroundColor Yellow
. .\.venv\Scripts\Activate.ps1

Write-Host "Installing dependencies from requirements.txt..." -ForegroundColor Yellow
pip install --upgrade pip | Out-Null
pip install -r requirements.txt

if (-not (Test-Path ".\.env")) {
    Write-Host "No .env found. Copying .env.template -> .env" -ForegroundColor Yellow
    Copy-Item ".\.env.template" ".\.env"
    Write-Host ""
    Write-Host "ACTION REQUIRED:" -ForegroundColor Red
    Write-Host "  Open lead-gen\.env and fill in:" -ForegroundColor Red
    Write-Host "    - BRIGHT_DATA_API_TOKEN   (rotated token from Bright Data dashboard)" -ForegroundColor Red
    Write-Host "    - BRIGHT_DATA_COLLECTOR_ID" -ForegroundColor Red
    Write-Host "    - FALLBACK_CONTACT_METHOD (your direct contact email)" -ForegroundColor Red
    Write-Host ""
    Write-Host "Then run: .\run.ps1 -SmokeTest" -ForegroundColor Red
    exit 0
} else {
    Write-Host ".env already exists, leaving it untouched." -ForegroundColor DarkGray
}

if (-not (Test-Path ".\output")) {
    New-Item -ItemType Directory -Path ".\output" | Out-Null
}

Write-Host ""
Write-Host "Setup complete. Next: .\run.ps1 -SmokeTest" -ForegroundColor Green
