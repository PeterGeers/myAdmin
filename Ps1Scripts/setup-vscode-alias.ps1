# Add VSCode alias to PowerShell profile
$profilePath = $PROFILE
$aliasContent = @"

# Fast VSCode alias - disables Copilot
function code-fast {
    param([string]`$path = ".")
    Start-Process "code" -ArgumentList `$path, "--disable-extension", "github.copilot", "--disable-extension", "github.copilot-chat"
}

# Override default 'code' command
function code {
    param([string]`$path = ".")
    Start-Process "code" -ArgumentList `$path, "--disable-extension", "github.copilot", "--disable-extension", "github.copilot-chat"
}
"@

# Create profile if it doesn't exist
if (-not (Test-Path $profilePath)) {
    New-Item -Path $profilePath -ItemType File -Force
}

# Add alias to profile
Add-Content -Path $profilePath -Value $aliasContent

Write-Host "VSCode aliases added to PowerShell profile" -ForegroundColor Green
Write-Host "Restart PowerShell or run: . `$PROFILE" -ForegroundColor Yellow
Write-Host "Then use: code-fast . (or just 'code .' will also disable Copilot)" -ForegroundColor Cyan