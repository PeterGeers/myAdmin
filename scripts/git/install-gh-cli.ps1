# Install GitHub CLI
Write-Host "Installing GitHub CLI..." -ForegroundColor Yellow

# Try winget first (most common on modern Windows)
try {
    Write-Host "Trying winget..." -ForegroundColor Cyan
    winget install --id GitHub.cli
    Write-Host "GitHub CLI installed successfully!" -ForegroundColor Green
} catch {
    Write-Host "Winget not available. Downloading manually..." -ForegroundColor Yellow
    
    # Download and install manually
    $url = "https://github.com/cli/cli/releases/latest/download/gh_2.40.1_windows_amd64.msi"
    $output = "$env:TEMP\gh-cli.msi"
    
    Write-Host "Downloading GitHub CLI..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $url -OutFile $output
    
    Write-Host "Installing..." -ForegroundColor Cyan
    Start-Process msiexec.exe -Wait -ArgumentList "/i $output /quiet"
    
    Write-Host "GitHub CLI installed!" -ForegroundColor Green
    Remove-Item $output
}

Write-Host ""
Write-Host "After installation, restart PowerShell and run:" -ForegroundColor Yellow
Write-Host "gh auth login" -ForegroundColor White
Write-Host "gh repo create myAdmin --public --source=. --remote=origin --push" -ForegroundColor White