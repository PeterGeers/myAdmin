Get-Process *code* | Select-Object Name, Id, CPU, WorkingSet
# Lean startup - close resource hogs first
Write-Host "Closing resource-heavy applications..." -ForegroundColor Yellow

# Close heavy apps
$processesToClose = @("Copilot", "Spotify", "ChatGPT", "OneDrive")
foreach ($proc in $processesToClose) {
    try {
        Stop-Process -Name $proc -Force -ErrorAction SilentlyContinue
        Write-Host "Closed $proc" -ForegroundColor Green
    } catch {
        Write-Host "$proc not running" -ForegroundColor Gray
    }
}

# Wait for processes to close
Start-Sleep -Seconds 2

# Start VSCode with minimal extensions
Write-Host "Starting VSCode (lean mode)..." -ForegroundColor Green
$rootDir = Split-Path -Parent $PSScriptRoot
Start-Process "code" -ArgumentList "$rootDir", "--disable-extension", "github.copilot", "--disable-extension", "github.copilot-chat"

Write-Host "VSCode starting in lean mode (no extensions)" -ForegroundColor Cyan