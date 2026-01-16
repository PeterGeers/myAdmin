#!/usr/bin/env pwsh
# Automated MySQL Database Backup Script
# Run this regularly to create timestamped backups

param(
    [string]$BackupDir = ".kiro/specs/incident",
    [switch]$Compress = $true
)

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupFile = "finance_backup_$timestamp.sql"
$backupPath = Join-Path $BackupDir $backupFile

Write-Host "🔄 Creating database backup..." -ForegroundColor Cyan
Write-Host "Backup file: $backupPath" -ForegroundColor Yellow

# Ensure backup directory exists
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

try {
    # Create backup using Docker exec
    docker exec myadmin-mysql-1 mysqldump -u peter -pPeterGeers1953 --single-transaction --routines --triggers finance > $backupPath
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Database backup created successfully" -ForegroundColor Green
        
        if ($Compress) {
            $zipFile = $backupPath -replace '\.sql$', '.zip'
            Compress-Archive -Path $backupPath -DestinationPath $zipFile -Force
            Remove-Item $backupPath
            Write-Host "✅ Backup compressed to: $zipFile" -ForegroundColor Green
        }
        
        # Keep only last 10 backups
        Get-ChildItem $BackupDir -Filter "finance_backup_*.zip" | 
        Sort-Object CreationTime -Descending | 
        Select-Object -Skip 10 | 
        Remove-Item -Force
            
        Write-Host "🧹 Cleaned up old backups (keeping last 10)" -ForegroundColor Yellow
        
    }
    else {
        Write-Host "❌ Backup failed!" -ForegroundColor Red
        exit 1
    }
}
catch {
    Write-Host "❌ Error creating backup: $_" -ForegroundColor Red
    exit 1
}