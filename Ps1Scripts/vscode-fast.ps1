# Fast VSCode launcher - always disables Copilot
param(
    [string]$Path = "."
)

Write-Host "Starting VSCode (Fast Mode - Copilot Disabled)..." -ForegroundColor Green

# Convert relative path to absolute
$absolutePath = Resolve-Path $Path -ErrorAction SilentlyContinue
if (-not $absolutePath) {
    $absolutePath = $Path
}

# Start VSCode with Copilot disabled
Start-Process "code" -ArgumentList $absolutePath, "--disable-extension", "github.copilot", "--disable-extension", "github.copilot-chat"

Write-Host "VSCode started for: $absolutePath" -ForegroundColor Cyan