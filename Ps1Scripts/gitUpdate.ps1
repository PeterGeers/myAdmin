# param([string]$message)
$message = "Update pdf processor to support eml file type"
# Change to myAdmin project root directory
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $scriptPath "..")

# Verify we're in the correct directory (should contain .git folder)
if (-not (Test-Path ".git")) {
    Write-Error "Not in a git repository. Current location: $(Get-Location)"
    exit 1
}

git add .
if ($message) {
    git commit -m "$message - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
}
else {
    git commit -m "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
}
git push origin main

# .\gitUpdate.ps1 "Your message here"
# Examples:
# .\gitUpdate.ps1 "Fixed frontend compilation errors"
# .\gitUpdate.ps1 "Added new features"
# .\gitUpdate.ps1 (no message, just date/time)