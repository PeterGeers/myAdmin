# Setup Git repository and push to GitHub
Write-Host "Setting up Git repository..." -ForegroundColor Yellow

# Initialize git if not already done
if (-not (Test-Path ".git")) {
    git init
    Write-Host "Git repository initialized" -ForegroundColor Green
}

# Add all files
git add .

# Create initial commit
git commit -m "Initial commit: myAdmin Dashboard with mobile responsive improvements"

# Add GitHub remote (replace YOUR_USERNAME with your GitHub username)
Write-Host "Add your GitHub remote URL:" -ForegroundColor Cyan
Write-Host "git remote add origin https://github.com/YOUR_USERNAME/myAdmin.git" -ForegroundColor White

# Push to GitHub
Write-Host "After adding remote, push with:" -ForegroundColor Cyan
Write-Host "git branch -M main" -ForegroundColor White
Write-Host "git push -u origin main" -ForegroundColor White

Write-Host ""
Write-Host "Don't forget to:" -ForegroundColor Yellow
Write-Host "1. Create the repository on GitHub first" -ForegroundColor White
Write-Host "2. Replace YOUR_USERNAME with your actual GitHub username" -ForegroundColor White