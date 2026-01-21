# Simple method to remove SQL backups from Git history
# Uses git filter-branch (built into Git)

$ErrorActionPreference = "Stop"

Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Red
Write-Host "║  REMOVE SQL BACKUPS FROM GIT HISTORY (SIMPLE METHOD)       ║" -ForegroundColor Red
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Red
Write-Host ""
Write-Host "⚠️  WARNING: This rewrites Git history!" -ForegroundColor Yellow
Write-Host ""

$confirm = Read-Host "Type 'YES' to proceed"
if ($confirm -ne "YES") {
    Write-Host "Cancelled" -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "Removing SQL backup files from Git history..." -ForegroundColor Cyan
Write-Host ""

# Remove the specific files from all commits
git filter-branch --force --index-filter `
    "git rm --cached --ignore-unmatch scripts/CICD/backups/mysql-backup-*.sql" `
    --prune-empty --tag-name-filter cat -- --all

if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Files removed from history" -ForegroundColor Green
    
    Write-Host ""
    Write-Host "Cleaning up..." -ForegroundColor Cyan
    
    # Clean up
    Remove-Item -Recurse -Force .git/refs/original/ -ErrorAction SilentlyContinue
    git reflog expire --expire=now --all
    git gc --prune=now --aggressive
    
    Write-Host "✓ Cleanup complete" -ForegroundColor Green
    Write-Host ""
    Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "║  SUCCESS - Files removed from Git history                 ║" -ForegroundColor Green
    Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Green
    Write-Host ""
    Write-Host "NEXT STEPS (REQUIRED):" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "1. Force push to GitHub:" -ForegroundColor White
    Write-Host "   git push origin --force --all" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "2. Verify on GitHub:" -ForegroundColor White
    Write-Host "   https://github.com/PeterGeers/myAdmin/tree/main/scripts/CICD/backups" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "3. If you have team members, they need to:" -ForegroundColor White
    Write-Host "   git fetch origin" -ForegroundColor Gray
    Write-Host "   git reset --hard origin/main" -ForegroundColor Gray
    Write-Host ""
}
else {
    Write-Host "✗ Failed to remove files" -ForegroundColor Red
    exit 1
}
