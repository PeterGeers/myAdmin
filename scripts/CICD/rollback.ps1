# Rollback Script - Restore from Database Backup
# Use this script to rollback to a previous database state

param(
    [Parameter(Mandatory = $false)]
    [string]$BackupFile = "",
    
    [switch]$ListBackups = $false,
    [switch]$Force = $false
)

$ErrorActionPreference = "Stop"

# Get the root directory
$RootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$BackupDir = Join-Path $RootDir "scripts\cicd\backups"
$LogDir = Join-Path $RootDir "scripts\cicd\logs"
$RollbackLog = Join-Path $LogDir "rollback-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"

# Create directories
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

# Ensure we're in the root directory
Push-Location $RootDir

function Write-Log {
    param($Message, $Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] [$Level] $Message"
    
    $color = switch ($Level) {
        "ERROR" { "Red" }
        "WARN" { "Yellow" }
        "SUCCESS" { "Green" }
        default { "White" }
    }
    
    Write-Host $logMessage -ForegroundColor $color
    Add-Content -Path $RollbackLog -Value $logMessage
}

function Exit-WithError {
    param($Message)
    Write-Log $Message "ERROR"
    exit 1
}

# List available backups
if ($ListBackups) {
    Write-Host "`nAvailable database backups:" -ForegroundColor Cyan
    Get-ChildItem $BackupDir -Filter "mysql-backup-*.sql" | 
    Sort-Object LastWriteTime -Descending |
    ForEach-Object {
        $size = [math]::Round($_.Length / 1MB, 2)
        Write-Host "  $($_.Name) - $size MB - $($_.LastWriteTime)" -ForegroundColor White
    }
    exit 0
}

Write-Log "=== Starting Database Rollback ===" "WARN"

# Select backup file
if (-not $BackupFile) {
    $latestBackup = Get-ChildItem $BackupDir -Filter "mysql-backup-*.sql" | 
    Sort-Object LastWriteTime -Descending | 
    Select-Object -First 1
    
    if (-not $latestBackup) {
        Exit-WithError "No backup files found in $BackupDir"
    }
    
    $BackupFile = $latestBackup.FullName
    Write-Log "Using latest backup: $($latestBackup.Name)" "INFO"
}
else {
    if (-not (Test-Path $BackupFile)) {
        Exit-WithError "Backup file not found: $BackupFile"
    }
}

# Confirm rollback
if (-not $Force) {
    Write-Host "`nWARNING: This will restore the database from backup." -ForegroundColor Red
    Write-Host "Current data will be REPLACED with backup data." -ForegroundColor Red
    Write-Host "Backup file: $BackupFile" -ForegroundColor Yellow
    $confirm = Read-Host "`nType 'ROLLBACK' to confirm"
    
    if ($confirm -ne "ROLLBACK") {
        Write-Log "Rollback cancelled by user" "INFO"
        exit 0
    }
}

# Get database credentials
$envFile = Get-Content "backend/.env"
$dbPassword = ($envFile | Select-String "MYSQL_ROOT_PASSWORD=(.+)").Matches.Groups[1].Value

if (-not $dbPassword) {
    Exit-WithError "Could not read MYSQL_ROOT_PASSWORD from backend/.env"
}

# Check MySQL container
$mysqlContainer = docker-compose ps -q mysql
if (-not $mysqlContainer) {
    Exit-WithError "MySQL container is not running. Start it with: docker-compose up -d mysql"
}

Write-Log "Restoring database from backup..." "INFO"

# Restore database
Get-Content $BackupFile | docker-compose exec -T mysql mysql -u root -p"$dbPassword" 2>&1 | Tee-Object -FilePath $RollbackLog -Append

if ($LASTEXITCODE -ne 0) {
    Exit-WithError "Database restore failed"
}

Write-Log "Database restored successfully" "SUCCESS"
Write-Log "Rollback completed" "SUCCESS"
Write-Log "Rollback log: $RollbackLog" "INFO"

# Return to original directory
Pop-Location

exit 0
