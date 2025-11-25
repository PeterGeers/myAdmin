# Complete VSCode cleanup script
Write-Host "Starting VSCode cleanup..." -ForegroundColor Red

# Step 1: Kill all VSCode processes
Write-Host "Killing all VSCode processes..." -ForegroundColor Yellow
try {
    Get-Process *code* | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
    Write-Host "All VSCode processes terminated" -ForegroundColor Green
} catch {
    Write-Host "No VSCode processes found or error killing them" -ForegroundColor Gray
}

# Step 2: Verify no processes remain
$remainingProcesses = Get-Process *code* -ErrorAction SilentlyContinue
if ($remainingProcesses) {
    Write-Host "Warning: Some VSCode processes still running:" -ForegroundColor Red
    $remainingProcesses | Select-Object Name, Id
} else {
    Write-Host "All VSCode processes successfully terminated" -ForegroundColor Green
}

# Step 3: Remove VSCode user data
Write-Host "Removing VSCode user data..." -ForegroundColor Yellow
$paths = @(
    "$env:APPDATA\Code",
    "$env:USERPROFILE\.vscode",
    "$env:APPDATA\Code - Insiders"
)

foreach ($path in $paths) {
    if (Test-Path $path) {
        try {
            Remove-Item $path -Recurse -Force -ErrorAction Stop
            Write-Host "Removed: $path" -ForegroundColor Green
        } catch {
            Write-Host "Failed to remove: $path - $($_.Exception.Message)" -ForegroundColor Red
        }
    } else {
        Write-Host "Not found: $path" -ForegroundColor Gray
    }
}

# Step 4: Clear temp files
Write-Host "Clearing temp VSCode files..." -ForegroundColor Yellow
$tempPaths = @(
    "$env:TEMP\vscode*",
    "$env:LOCALAPPDATA\Programs\Microsoft VS Code"
)

foreach ($tempPath in $tempPaths) {
    if (Test-Path $tempPath) {
        try {
            Remove-Item $tempPath -Recurse -Force -ErrorAction SilentlyContinue
            Write-Host "Cleared: $tempPath" -ForegroundColor Green
        } catch {
            Write-Host "Could not clear: $tempPath" -ForegroundColor Yellow
        }
    }
}

Write-Host "`nCleanup complete!" -ForegroundColor Green
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Uninstall VSCode from Windows Settings > Apps" -ForegroundColor White
Write-Host "2. Restart your computer" -ForegroundColor White
Write-Host "3. Download fresh VSCode from https://code.visualstudio.com/" -ForegroundColor White
Write-Host "4. Install and test with: code --version" -ForegroundColor White