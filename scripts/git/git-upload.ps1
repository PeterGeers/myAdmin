# Git Upload Script for myAdmin Repository

param(
    [string]$Message = "Update: $(Get-Date -Format 'yyyy-MM-dd HH:mm')",
    [switch]$Initial
)

Write-Host "myAdmin Git Upload Script" -ForegroundColor Green
Write-Host "Repository: myAdmin" -ForegroundColor Cyan

# Validate GitHub CLI
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Host "Error: GitHub CLI (gh) not found. Please install it first." -ForegroundColor Red
    exit 1
}

# Test GitHub authentication
try {
    $username = gh api user --jq .login 2>$null
    if (-not $username) {
        Write-Host "Error: Not authenticated with GitHub CLI. Run 'gh auth login' first." -ForegroundColor Red
        exit 1
    }
}
catch {
    Write-Host "Error: GitHub CLI authentication failed. Run 'gh auth login' first." -ForegroundColor Red
    exit 1
}

# Check if git is initialized
if (-not (Test-Path ".git")) {
    Write-Host "Initializing Git repository..." -ForegroundColor Yellow
    git init
    git branch -M main
}

# Check if remote exists
$remoteExists = git remote get-url origin 2>$null
if (-not $remoteExists) {
    Write-Host "Adding GitHub remote..." -ForegroundColor Yellow
    git remote add origin "https://github.com/$username/myAdmin.git"
    Write-Host "Remote added: https://github.com/$username/myAdmin.git" -ForegroundColor Green
}

# Dynamic submodule cleanup - find all .git folders in subdirectories
$subGitFolders = Get-ChildItem -Path . -Recurse -Directory -Name ".git" -Depth 2 | Where-Object { $_ -ne ".git" }
foreach ($folder in $subGitFolders) {
    Write-Host "Removing $folder (submodule cleanup)..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $folder
}

# Add all files
Write-Host "Adding files..." -ForegroundColor Yellow
git add .

# Run GitGuardian secret scan before committing
. "$PSScriptRoot/../security/Invoke-GitGuardianScan.ps1"
$scanResult = Invoke-GitGuardianScan -AllowSkip $true -UseWriteLog $false

# Check if scan result is numeric and not 0
if ($scanResult -is [int] -and $scanResult -ne 0) {
    Write-Host "Aborting commit to protect your secrets." -ForegroundColor Red
    exit 1
}
elseif ($scanResult -isnot [int]) {
    # If result is not an integer, something went wrong
    Write-Host "Warning: Unexpected scan result: $scanResult" -ForegroundColor Yellow
    Write-Host "Continuing with commit..." -ForegroundColor Yellow
}

Write-Host ""

# Check if there are changes to commit
$status = git status --porcelain
if (-not $status) {
    Write-Host "No changes to commit" -ForegroundColor Green
    exit 0
}

# Commit changes
Write-Host "Committing changes..." -ForegroundColor Yellow
if ($Initial) {
    $currentDate = Get-Date -Format "yyyyMMdd"
    git commit -m "$currentDate commit: myAdmin Dashboard with mobile responsive improvements

Features:
- Mobile responsive tables with horizontal scroll
- Compact dropdown filters
- ProductCard with size selection
- Security fixes (XSS, hardcoded credentials)
- Lazy loading components
- AWS S3 deployment ready"
}
else {
    git commit -m $Message
}

# Push to GitHub
Write-Host "Pushing to GitHub..." -ForegroundColor Yellow
git push -u origin main 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Push failed. Attempting to resolve..." -ForegroundColor Red
    
    # Pull remote changes and try again
    Write-Host "Repository is behind remote. Pulling changes..." -ForegroundColor Yellow
    git pull origin main --no-edit 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Merge conflicts detected. Please resolve manually." -ForegroundColor Red
        Write-Host "Run: git status" -ForegroundColor White
        exit 1
    }
    
    git push -u origin main 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Push failed after pull. Check network and permissions." -ForegroundColor Red
        exit 1
    }
    Write-Host "Successfully uploaded after pull!" -ForegroundColor Green
}
else {
    Write-Host "Successfully uploaded to GitHub!" -ForegroundColor Green
}

# Get repository URL (using cached username)
$repoUrl = "https://github.com/$username/myAdmin"
Write-Host "Repository URL: $repoUrl" -ForegroundColor Cyan

Write-Host ""
Write-Host "Upload complete!" -ForegroundColor Green