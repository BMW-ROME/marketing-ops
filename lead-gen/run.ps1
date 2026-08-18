# lead-gen/run.ps1
# Runs the LeadGen pipeline locally. Defaults to a small smoke-test batch.
# Usage:
#   .\run.ps1 -SmokeTest            (small batch, ~10-20 leads, recommended first run)
#   .\run.ps1                       (full configured batch, only after smoke test passes)

param(
    [switch]$SmokeTest
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".\.env")) {
    Write-Host "Missing .env. Run .\setup.ps1 first." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path ".\.venv")) {
    Write-Host "Missing virtual environment. Run .\setup.ps1 first." -ForegroundColor Red
    exit 1
}

. .\.venv\Scripts\Activate.ps1

# Basic guard: confirm required vars are not still placeholders before spending API calls.
$envContent = Get-Content ".\.env" -Raw
if ($envContent -match "your_bright_data_api_token_here" -or $envContent -match "your_collector_id_here") {
    Write-Host "ERROR: .env still contains placeholder values." -ForegroundColor Red
    Write-Host "Edit lead-gen\.env and set your real (rotated) Bright Data token and collector ID." -ForegroundColor Red
    exit 1
}

if ($SmokeTest) {
    Write-Host "Running SMOKE TEST batch (small sample, recommended first run)..." -ForegroundColor Cyan
    python lead_generator.py --limit 15 --output ".\output\smoke_test_leads.csv"
    Write-Host ""
    Write-Host "Smoke test complete. Review .\output\smoke_test_leads.csv manually before scaling up." -ForegroundColor Green
    Write-Host "Use LEAD_REVIEW_TEMPLATE.csv as the format for manual approval/status tracking." -ForegroundColor Green
} else {
    Write-Host "Running FULL batch..." -ForegroundColor Cyan
    python lead_generator.py --output ".\output\leads_$(Get-Date -Format yyyyMMdd_HHmmss).csv"
}
