#!/usr/bin/env pwsh
# ⚠️⚠️⚠️ DANGEROUS SCRIPT - DELETES ALL DATA ⚠️⚠️⚠️
# This script will DELETE ALL DATABASE DATA
# Only use if you want to completely reset the system

Write-Host "⚠️⚠️⚠️ DANGER: This will DELETE ALL DATABASE DATA ⚠️⚠️⚠️" -ForegroundColor Red -BackgroundColor Yellow
Write-Host "This includes:" -ForegroundColor Red
Write-Host "- All transactions" -ForegroundColor Red  
Write-Host "- All views and tables" -ForegroundColor Red
Write-Host "- All historical data" -ForegroundColor Red
Write-Host "- Everything in the finance database" -ForegroundColor Red

$confirmation = Read-Host "Type 'DELETE ALL MY DATA' to confirm (anything else cancels)"

if ($confirmation -ne "DELETE ALL MY DATA") {
    Write-Host "✅ Cancelled - no data deleted" -ForegroundColor Green
    exit 0
}

$secondConfirmation = Read-Host "Are you ABSOLUTELY SURE? Type 'YES DELETE EVERYTHING'"

if ($secondConfirmation -ne "YES DELETE EVERYTHING") {
    Write-Host "✅ Cancelled - no data deleted" -ForegroundColor Green
    exit 0
}

Write-Host "💀 Deleting all data..." -ForegroundColor Red
docker-compose down -v
Remove-Item -Recurse -Force ./mysql_data -ErrorAction SilentlyContinue
docker-compose up -d

Write-Host "💀 All data has been deleted" -ForegroundColor Red