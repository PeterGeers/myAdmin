param([string]$message)

git add .
if ($message) {
    git commit -m "$message - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
}
else {
    git commit -m "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
}

# .\gitUpdate.ps1 "Your message here"
# Examples:
# .\gitUpdate.ps1 "Fixed frontend compilation errors"
# .\gitUpdate.ps1 "Added new features"
# .\gitUpdate.ps1 (no message, just date/time)