# Fix API key leak from Git history
Write-Host "Removing API key from Git history..." -ForegroundColor Red

# Remove the exposed file from Git history
git filter-branch --force --index-filter "git rm --cached --ignore-unmatch .env.docker" --prune-empty --tag-name-filter cat -- --all

# Force push to overwrite GitHub history
Write-Host "Force pushing to GitHub..." -ForegroundColor Yellow
git push origin --force --all

Write-Host "✅ API key removed from Git history" -ForegroundColor Green
Write-Host "⚠️  Remember to update .env.docker with your NEW API key" -ForegroundColor Yellow