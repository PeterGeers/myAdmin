# Remove SQL Backup Files from Git History
# WARNING: This rewrites Git history!

$ErrorActionPreference = "Stop"

Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Red
Write-Host "║  REMOVE SENSITIVE SQL BACKUPS FROM GIT HISTORY             ║" -ForegroundColor Red
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Red
Write-Host ""
Write-Host "⚠️  WARNING: This will rewrite Git history!" -ForegroundColor Yellow
Write-Host ""
Write-Host "Files to remove:" -ForegroundColor Cyan
Write-Host "  - scripts/CICD/backups/mysql-backup-20260118-203510.sql" -ForegroundColor Gray
Write-Host "  - scripts/CICD/backups/mysql-backup-20260118-220153.sql" -ForegroundColor Gray
Write-Host "  - Any other *.sql files in backups/" -ForegroundColor Gray
Write-Host ""
Write-Host "This will:" -ForegroundColor Yellow
Write-Host "  1. Remove files from all commits" -ForegroundColor Gray
Write-Host "  2. Rewrite Git history" -ForegroundColor Gray
Write-Host "  3. Require force push to GitHub" -ForegroundColor Gray
Write-Host ""

$confirm = Read-Host "Continue? Type 'YES' to proceed"

if ($confirm -ne "YES") {
    Write-Host "Cancelled" -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "Step 1: Installing BFG Repo-Cleaner..." -ForegroundColor Cyan

# Check if BFG is available
$bfgPath = "bfg.jar"
if (-not (Test-Path $bfgPath)) {
    Write-Host "Downloading BFG Repo-Cleaner..." -ForegroundColor Yellow
    $bfgUrl = "https://repo1.maven.org/maven2/com/madgag/bfg/1.14.0/bfg-1.14.0.jar"
    Invoke-WebRequest -Uri $bfgUrl -OutFile $bfgPath
    Write-Host "✓ Downloaded BFG" -ForegroundColor Green
}

Write-Host ""
Write-Host "Step 2: Removing SQL files from Git history..." -ForegroundColor Cyan

# Use BFG to remove all SQL files from backups folder
java -jar $bfgPath --delete-files "mysql-backup-*.sql" --no-blob-protection

if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ BFG failed" -ForegroundColor Red
    exit 1
}

Write-Host "✓ Files removed from history" -ForegroundColor Green

Write-Host ""
Write-Host "Step 3: Cleaning up Git repository..." -ForegroundColor Cyan

# Clean up
git reflog expire --expire=now --all
git gc --prune=now --aggressive

Write-Host "✓ Repository cleaned" -ForegroundColor Green

Write-Host ""
Write-Host "Step 4: Verifying removal..." -ForegroundColor Cyan

# Check if files still exist in history
$check = git log --all --full-history --oneline -- "scripts/CICD/backups/*.sql"

if ($check) {
    Write-Host "⚠️  Files may still exist in some commits" -ForegroundColor Yellow
    Write-Host $check
}
else {
    Write-Host "✓ Files successfully removed from history" -ForegroundColor Green
}

Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║  CLEANUP COMPLETE                                          ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "IMPORTANT: Next Steps" -ForegroundColor Yellow
Write-Host "=====================" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. Force push to GitHub (REQUIRED):" -ForegroundColor White
Write-Host "   git push origin --force --all" -ForegroundColor Cyan
Write-Host "   git push origin --force --tags" -ForegroundColor Cyan
Write-Host ""
Write-Host "2. Notify team members:" -ForegroundColor White
Write-Host "   - They need to re-clone the repository" -ForegroundColor Gray
Write-Host "   - Or run: git fetch origin && git reset --hard origin/main" -ForegroundColor Gray
Write-Host ""
Write-Host "3. Verify on GitHub:" -ForegroundColor White
Write-Host "   - Check that backup files are gone" -ForegroundColor Gray
Write-Host "   - https://github.com/PeterGeers/myAdmin/tree/main/scripts/CICD/backups" -ForegroundColor Gray
Write-Host ""
Write-Host "⚠️  Security Note:" -ForegroundColor Red
Write-Host "   - Files are removed from Git history" -ForegroundColor Gray
Write-Host "   - GitHub may cache them for ~24 hours" -ForegroundColor Gray
Write-Host "   - Consider rotating any credentials in those backups" -ForegroundColor Gray
Write-Host ""
