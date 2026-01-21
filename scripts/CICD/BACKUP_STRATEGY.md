# Database Backup Strategy

## ⚠️ SECURITY WARNING

**NEVER commit SQL backups to Git!**

SQL backups contain:

- Customer personal data (GDPR sensitive)
- Financial information
- Authentication credentials
- Business-critical data

## Current Status

✅ **Fixed**: Added `.gitignore` rules to exclude SQL backups  
✅ **Fixed**: Removed backup file from repository  
⚠️ **Action Required**: Remove from Git history if already committed

## Proper Backup Locations

### Option 1: OneDrive (Current Setup) ✅

```powershell
# Windows with OneDrive - CURRENT LOCATION
C:\Users\peter\OneDrive\MariaDB\finance
```

**Pros:**

- ✅ Automatic cloud backup
- ✅ Version history available (OneDrive keeps previous versions)
- ✅ Protected against hardware failure
- ✅ Easy access from anywhere
- ✅ Already configured and working
- ✅ Completely separate from Git repository

**Cons:**

- OneDrive storage limits (check available space)
- Requires OneDrive subscription

**Current Status:** This is your active backup location - keep using it!

### Option 2: External Backup Server

```bash
# Automated daily backups to remote server
mysqldump -u user -p database | ssh backup-server "cat > /backups/mysql-$(date +%Y%m%d).sql"
```

### Option 3: AWS S3 with Encryption

```bash
# Backup to S3 with server-side encryption
mysqldump -u user -p database | gzip | aws s3 cp - s3://my-backups/mysql-$(date +%Y%m%d).sql.gz --sse AES256
```

### Option 4: Local Encrypted Drive (Alternative)

```bash
# Backup to local encrypted volume (NOT in Git repo)
mysqldump -u user -p database > /mnt/encrypted-backup/mysql-$(date +%Y%m%d).sql
```

### Option 5: Network Attached Storage (NAS)

```bash
# Backup to NAS with automatic versioning
mysqldump -u user -p database > /mnt/nas/backups/mysql-$(date +%Y%m%d).sql
```

## Backup Script Location

**Previous (WRONG)**: `scripts/CICD/backups/` ❌ (In Git repo)  
**Current (CORRECT)**: `C:\Users\peter\OneDrive\MariaDB\finance` ✅ (OneDrive - safe!)

## Recommended Backup Structure

For your OneDrive location:

```
C:\Users\peter\OneDrive\MariaDB\finance\
├── daily\
│   ├── mysql-20260120.sql
│   ├── mysql-20260119.sql
│   └── ... (keep 7 days)
├── weekly\
│   ├── mysql-week-03.sql
│   └── ... (keep 4 weeks)
└── monthly\
    ├── mysql-2026-01.sql
    └── ... (keep 12 months)
```

**Note:** OneDrive automatically provides version history, so you have additional protection even if you overwrite files.

## Automated Backup Script (Windows/PowerShell)

Create: `scripts/backup-mysql.ps1` (NOT in CICD folder)

```powershell
# MySQL Backup Script for Windows - Run daily via Task Scheduler

$BackupDir = "C:\Users\peter\OneDrive\MariaDB\finance\daily"
$Date = Get-Date -Format "yyyyMMdd"
$DbName = "finance"
$DbUser = "root"
$DbPassword = "your_password"  # Consider using secure credential storage

# Ensure backup directory exists
if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir -Force
}

# Create backup
$BackupFile = "$BackupDir\mysql-$Date.sql"
& mysqldump -u $DbUser -p$DbPassword $DbName > $BackupFile

if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Backup created: $BackupFile" -ForegroundColor Green

    # Optional: Compress the backup
    # Compress-Archive -Path $BackupFile -DestinationPath "$BackupFile.zip"
    # Remove-Item $BackupFile

    # Keep only last 7 days (OneDrive version history provides additional protection)
    Get-ChildItem $BackupDir -Filter "mysql-*.sql" |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } |
        Remove-Item -Force

    Write-Host "✓ Old backups cleaned up" -ForegroundColor Green
} else {
    Write-Host "✗ Backup failed!" -ForegroundColor Red
    exit 1
}
```

## Windows Task Scheduler Setup

Create automated daily backups:

```powershell
# Create scheduled task for daily backup at 2 AM
$Action = New-ScheduledTaskAction -Execute "PowerShell.exe" `
    -Argument "-ExecutionPolicy Bypass -File C:\Users\peter\aws\myAdmin\scripts\backup-mysql.ps1"

$Trigger = New-ScheduledTaskTrigger -Daily -At 2:00AM

$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable

Register-ScheduledTask -TaskName "MySQL Daily Backup" `
    -Action $Action -Trigger $Trigger -Settings $Settings `
    -Description "Daily backup of MySQL finance database to OneDrive"
```

## Backup Verification

Always verify backups can be restored:

```bash
# Test restore to temporary database
mysql -u root -p -e "CREATE DATABASE test_restore"
gunzip < backup.sql.gz | mysql -u root -p test_restore
mysql -u root -p -e "DROP DATABASE test_restore"
```

## Encryption

### Encrypt Backup

```bash
# Backup and encrypt
mysqldump -u user -p database | gzip | openssl enc -aes-256-cbc -salt -out backup.sql.gz.enc
```

### Decrypt Backup

```bash
# Decrypt and restore
openssl enc -d -aes-256-cbc -in backup.sql.gz.enc | gunzip | mysql -u user -p database
```

## Retention Policy

- **Daily**: Keep 7 days
- **Weekly**: Keep 4 weeks
- **Monthly**: Keep 12 months
- **Yearly**: Keep 7 years (compliance)

## Compliance

### GDPR Requirements

- Backups must be encrypted
- Access must be logged
- Data must be deletable on request
- Backups must be in EU (if applicable)

### Security Best Practices

- ✅ Encrypt backups at rest
- ✅ Encrypt backups in transit
- ✅ Limit access (principle of least privilege)
- ✅ Regular restore testing
- ✅ Off-site backup copies
- ❌ NEVER commit to Git
- ❌ NEVER store in public locations
- ❌ NEVER share via email/Slack

## Disaster Recovery

### Recovery Time Objective (RTO)

- Target: < 1 hour

### Recovery Point Objective (RPO)

- Target: < 24 hours (daily backups)

### Recovery Procedure

1. Stop application
2. Restore database from latest backup
3. Verify data integrity
4. Restart application
5. Test functionality

## Monitoring

Set up alerts for:

- Backup failures
- Backup size anomalies
- Missing backups
- Restore test failures

## Git History Cleanup

If SQL backups were already committed:

```bash
# Remove from Git history (DESTRUCTIVE!)
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch scripts/CICD/backups/*.sql" \
  --prune-empty --tag-name-filter cat -- --all

# Force push (coordinate with team!)
git push origin --force --all
git push origin --force --tags

# Clean up local repo
rm -rf .git/refs/original/
git reflog expire --expire=now --all
git gc --prune=now --aggressive
```

⚠️ **Warning**: This rewrites Git history. Coordinate with your team!

## Alternative: BFG Repo-Cleaner

Easier way to remove sensitive files:

```bash
# Install BFG
brew install bfg  # or download from https://rtyley.github.io/bfg-repo-cleaner/

# Remove all SQL files
bfg --delete-files '*.sql' --no-blob-protection

# Clean up
git reflog expire --expire=now --all && git gc --prune=now --aggressive
```

## Summary

✅ **DO**:

- Store backups outside Git repository
- Encrypt backups
- Test restores regularly
- Use automated backup scripts
- Monitor backup health

❌ **DON'T**:

- Commit SQL backups to Git
- Store backups in public locations
- Share backups via insecure channels
- Forget to test restores
- Ignore backup failures

---

**Last Updated**: January 20, 2026  
**Status**: ⚠️ Action Required - Remove from Git history if committed
