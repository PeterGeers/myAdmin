# Migrate data from manual containers to docker-compose
Write-Host "🔄 Migrating to docker-compose with data preservation..." -ForegroundColor Green

# Step 1: Export data from mysql-speed-test
Write-Host "1. Exporting data from mysql-speed-test..." -ForegroundColor Yellow
docker exec mysql-speed-test mysqldump -u peter -pPeterGeers1953 finance > compose_migration_backup.sql

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Data exported successfully" -ForegroundColor Green
} else {
    Write-Host "❌ Export failed" -ForegroundColor Red
    exit 1
}

# Step 2: Stop manual containers
Write-Host "2. Stopping manual containers..." -ForegroundColor Yellow
docker stop eloquent_keller mysql-speed-test
docker rm eloquent_keller mysql-speed-test

# Step 3: Start docker-compose containers
Write-Host "3. Starting docker-compose containers..." -ForegroundColor Yellow
docker-compose up -d --build

# Wait for MySQL to be ready
Write-Host "4. Waiting for MySQL to be ready..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

# Step 5: Import data into new container
Write-Host "5. Importing data into docker-compose MySQL..." -ForegroundColor Yellow
Get-Content "compose_migration_backup.sql" | docker exec -i myadmin-mysql-1 mysql -u peter -pPeterGeers1953 finance

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Data imported successfully" -ForegroundColor Green
    Remove-Item "compose_migration_backup.sql"
    Write-Host "✅ Migration complete! Using docker-compose containers" -ForegroundColor Green
} else {
    Write-Host "❌ Import failed. Backup preserved: compose_migration_backup.sql" -ForegroundColor Red
}