# Disable Copilot globally in VSCode user settings
$userSettingsPath = "$env:APPDATA\Code\User\settings.json"

# Read existing settings
if (Test-Path $userSettingsPath) {
    $settings = Get-Content $userSettingsPath | ConvertFrom-Json
} else {
    $settings = @{}
}

# Add Copilot disable settings
$settings | Add-Member -NotePropertyName "github.copilot.enable" -NotePropertyValue @{
    "*" = $false
    "plaintext" = $false
    "markdown" = $false
    "scminput" = $false
} -Force

# Save settings
$settings | ConvertTo-Json -Depth 10 | Set-Content $userSettingsPath

Write-Host "Copilot disabled globally in VSCode" -ForegroundColor Green