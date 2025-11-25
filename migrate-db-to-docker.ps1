# Migrate MySQL database from localhost to Docker
Write-Host "Migrating MySQL database to Docker..." -ForegroundColor Green

# Load environment variables
$envFile = Get-Content "backend\.env" | Where-Object { $_ -match "=" }
$env:DB_NAME = ($envFile | Where-Object { $_ -match "^DB_NAME=" }) -replace "DB_NAME=", ""
$env:DB_USER = ($envFile | Where-Object { $_ -match "^DB_USER=" }) -replace "DB_USER=", ""
$env:DB_PASSWORD = ($envFile | Where-Object { $_ -match "^DB_PASSWORD=" }) -replace "DB_PASSWORD=", ""

# Try root user if peter fails
Write-Host "If export fails, we'll try with root user" -ForegroundColor Yellow

Write-Host "Database: $env:DB_NAME" -ForegroundColor Yellow

# Step 1: Export from localhost MySQL using Docker
Write-Host "1. Exporting from localhost MySQL..." -ForegroundColor Cyan
$dumpFile = "mysql_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss').sql"

# Try common MySQL installation paths
$mysqlPaths = @(
    "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe",
    "C:\Program Files\MySQL\MySQL Server 5.7\bin\mysqldump.exe",
    "C:\xampp\mysql\bin\mysqldump.exe",
    "C:\wamp64\bin\mysql\mysql8.0.31\bin\mysqldump.exe"
)

$mysqldumpPath = $null
foreach ($path in $mysqlPaths) {
    if (Test-Path $path) {
        $mysqldumpPath = $path
        break
    }
}

if ($mysqldumpPath) {
    Write-Host "Using mysqldump at: $mysqldumpPath" -ForegroundColor Yellow
    
    # Try with configured user first
    Write-Host "Trying with user: $env:DB_USER" -ForegroundColor Cyan
    & $mysqldumpPath -h localhost -u $env:DB_USER -p$env:DB_PASSWORD $env:DB_NAME > $dumpFile 2>$null
    
    # If that fails, try with root
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed with $env:DB_USER, trying with root..." -ForegroundColor Yellow
        $rootPassword = Read-Host "Enter MySQL root password" -AsSecureString
        $rootPasswordText = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($rootPassword))
        & $mysqldumpPath -h localhost -u root -p$rootPasswordText $env:DB_NAME > $dumpFile 2>$null
    }
} else {
    Write-Host "❌ mysqldump not found. Please install MySQL client or add to PATH" -ForegroundColor Red
    Write-Host "Alternative: Export manually from your MySQL client" -ForegroundColor Yellow
    exit 1
}

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Database exported to $dumpFile" -ForegroundColor Green
} else {
    Write-Host "❌ Export failed with both users" -ForegroundColor Red
    Write-Host "Please check your MySQL credentials or export manually" -ForegroundColor Yellow
    exit 1
}

# Step 2: Start Docker MySQL (if not running)
Write-Host "2. Starting Docker MySQL container..." -ForegroundColor Cyan
docker-compose up -d mysql

# Wait for MySQL to be ready
Write-Host "3. Waiting for MySQL container to be ready..." -ForegroundColor Cyan
Start-Sleep -Seconds 10

# Step 3: Import into Docker MySQL
Write-Host "4. Importing into Docker MySQL..." -ForegroundColor Cyan
Get-Content $dumpFile | docker exec -i myadmin-mysql-1 mysql -u $env:DB_USER -p$env:DB_PASSWORD $env:DB_NAME

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Database imported successfully" -ForegroundColor Green
    Write-Host "5. Cleaning up backup file..." -ForegroundColor Cyan
    Remove-Item $dumpFile
    Write-Host "✅ Migration complete!" -ForegroundColor Green
} else {
    Write-Host "❌ Import failed. Backup file preserved: $dumpFile" -ForegroundColor Red
    exit 1
}