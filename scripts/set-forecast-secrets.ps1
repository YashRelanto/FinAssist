# Set Edge Function secrets for train-forecast (must match .env).
#
# Why login alone may fail on Windows:
#   npx supabase secrets set needs SUPABASE_ACCESS_TOKEN (Management API).
#   Browser login stores a token in Credential Manager that secrets set may not see via npx.
#
# Option A (recommended): create a token at https://supabase.com/dashboard/account/tokens
#   then run:
#     $env:SUPABASE_ACCESS_TOKEN = "sbp_...."
#     .\scripts\set-forecast-secrets.ps1
#
# Option B: Dashboard → Project → Edge Functions → Secrets (no CLI)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not $env:SUPABASE_ACCESS_TOKEN) {
    Write-Host ""
    Write-Host "SUPABASE_ACCESS_TOKEN is not set." -ForegroundColor Yellow
    Write-Host "1. Open https://supabase.com/dashboard/account/tokens"
    Write-Host "2. Generate a token (name: finassist-cli)"
    Write-Host "3. In THIS terminal run:"
    Write-Host '   $env:SUPABASE_ACCESS_TOKEN = "sbp_YOUR_TOKEN_HERE"'
    Write-Host "4. Run this script again: .\scripts\set-forecast-secrets.ps1"
    Write-Host ""
    Write-Host "Or set secrets in the Dashboard:"
    Write-Host "https://supabase.com/dashboard/project/wequiafwuvugkzgqzety/functions"
    exit 1
}

$envFile = Join-Path $repoRoot ".env"
if (-not (Test-Path $envFile)) {
    Write-Error ".env not found. Copy .env.example and set FORECAST_CRON_SECRET."
}

$lines = Get-Content $envFile
$cronSecret = (($lines | Where-Object { $_ -match '^FORECAST_CRON_SECRET=' }) -replace '^FORECAST_CRON_SECRET=', '').Trim()
$workerUrl = (($lines | Where-Object { $_ -match '^TRAINING_WORKER_URL=' }) -replace '^TRAINING_WORKER_URL=', '').Trim()

if ([string]::IsNullOrWhiteSpace($cronSecret)) {
    Write-Error "FORECAST_CRON_SECRET missing in .env"
}
if ([string]::IsNullOrWhiteSpace($workerUrl)) {
    Write-Error "TRAINING_WORKER_URL missing in .env"
}

if ($workerUrl -match 'localhost|127\.0\.0\.1|0\.0\.0\.0') {
    Write-Host ""
    Write-Host "WARNING: TRAINING_WORKER_URL is local ($workerUrl)." -ForegroundColor Yellow
    Write-Host "Supabase Edge Functions run in the cloud and cannot reach your machine."
    Write-Host "Use a public HTTPS URL (deployed API, Cloudflare Tunnel, ngrok, etc.) or cron training will fail with 502."
    Write-Host ""
}

Write-Host "Setting Edge Function secrets on project wequiafwuvugkzgqzety ..."
& npx supabase secrets set `
    --project-ref wequiafwuvugkzgqzety `
    "FORECAST_CRON_SECRET=$cronSecret" `
    "TRAINING_WORKER_URL=$workerUrl"

if ($LASTEXITCODE -ne 0) {
    Write-Error "supabase secrets set failed (exit $LASTEXITCODE)"
}

Write-Host "Done. Test (expect 502 until TRAINING_WORKER_URL is publicly reachable):"
Write-Host '  try { Invoke-WebRequest -Method POST -Uri "https://wequiafwuvugkzgqzety.supabase.co/functions/v1/train-forecast" -ContentType "application/json" -Body "{}" } catch { $_.Exception.Response.StatusCode.value__; (New-Object IO.StreamReader($_.Exception.Response.GetResponseStream())).ReadToEnd() }'
