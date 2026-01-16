# Simple MySQL migration - manual approach
Write-Host "Simple MySQL Migration Guide" -ForegroundColor Green

Write-Host "1. Open your MySQL client (MySQL Workbench, phpMyAdmin, etc.)" -ForegroundColor Cyan
Write-Host "2. Export the 'finance' database to a SQL file" -ForegroundColor Cyan
Write-Host "3. Save it as 'finance_backup.sql' in this directory" -ForegroundColor Cyan
Write-Host "4. Run this script again to import into Docker" -ForegroundColor Cyan

if (Test-Path "finance_backup.sql") {
    Write-Host "Found finance_backup.sql - importing to Docker..." -ForegroundColor Green
    
    # Wait for MySQL container to be ready
    Write-Host "Waiting for Docker MySQL to be ready..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5
    
    # Create database and user in Docker MySQL first
    Write-Host "Setting up database and user..." -ForegroundColor Yellow
    docker exec myadmin-mysql-1 mysql -u root -pPeterGeers1953 -e "CREATE DATABASE IF NOT EXISTS finance;"
    docker exec myadmin-mysql-1 mysql -u root -pPeterGeers1953 -e "CREATE USER IF NOT EXISTS 'peter'@'%' IDENTIFIED BY 'PeterGeers1953';"
    docker exec myadmin-mysql-1 mysql -u root -pPeterGeers1953 -e "GRANT ALL PRIVILEGES ON finance.* TO 'peter'@'%';"
    docker exec myadmin-mysql-1 mysql -u root -pPeterGeers1953 -e "FLUSH PRIVILEGES;"
    
    # Import into Docker MySQL
    Write-Host "Importing data..." -ForegroundColor Yellow
    Get-Content "finance_backup.sql" | docker exec -i myadmin-mysql-1 mysql -u root -pPeterGeers1953 finance
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Database imported successfully!" -ForegroundColor Green
        Write-Host "You can now use Docker MySQL on port 3307" -ForegroundColor Green
    } else {
        Write-Host "❌ Import failed" -ForegroundColor Red
    }
} else {
    Write-Host "Please create finance_backup.sql first" -ForegroundColor Yellow
}