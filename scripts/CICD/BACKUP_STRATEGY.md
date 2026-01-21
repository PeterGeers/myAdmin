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

### Option 1: External Backup Server (Recommended)

```bash
# Automated daily backups to remote server
mysqldump -u user -p database | ssh backup-server "cat > /backups/mysql-$(date +%Y%m%d).sql"
```

### Option 2: AWS S3 with Encryption

```bash
# Backup to S3 with server-side encryption
mysqldump -u user -p database | gzip | aws s3 cp - s3://my-backups/mysql-$(date +%Y%m%d).sql.gz --sse AES256
```

### Option 3: Local Encrypted Drive

```bash
# Backup to local encrypted volume (NOT in Git repo)
mysqldump -u user -p database > /mnt/encrypted-backup/mysql-$(date +%Y%m%d).sql
```

### Option 4: Network Attached Storage (NAS)

```bash
# Backup to NAS with automatic versioning
mysqldump -u user -p database > /mnt/nas/backups/mysql-$(date +%Y%m%d).sql
```

## Backup Script Location

**Current**: `scripts/CICD/backups/` ❌ (In Git repo - WRONG!)  
**Correct**: `/var/backups/mysql/` or similar (Outside Git repo)

## Recommended Backup Structure

```
/var/backups/mysql/
├── daily/
│   ├── mysql-20260120.sql.gz
│   ├── mysql-20260119.sql.gz
│   └── ... (keep 7 days)
├── weekly/
│   ├── mysql-week-03.sql.gz
│   └── ... (keep 4 weeks)
└── monthly/
    ├── mysql-2026-01.sql.gz
    └── ... (keep 12 months)
```

## Automated Backup Script

Create: `/usr/local/bin/mysql-backup.sh`

```bash
#!/bin/bash
# MySQL Backup Script - Run daily via cron

BACKUP_DIR="/var/backups/mysql/daily"
DATE=$(date +%Y%m%d)
DB_NAME="finance"
DB_USER="backup_user"
DB_PASS="secure_password"

# Create backup
mysqldump -u $DB_USER -p$DB_PASS $DB_NAME | gzip > "$BACKUP_DIR/mysql-$DATE.sql.gz"

# Keep only last 7 days
find $BACKUP_DIR -name "mysql-*.sql.gz" -mtime +7 -delete

# Optional: Upload to S3
# aws s3 cp "$BACKUP_DIR/mysql-$DATE.sql.gz" s3://my-backups/
```

## Cron Schedule

Add to crontab:

```bash
# Daily backup at 2 AM
0 2 * * * /usr/local/bin/mysql-backup.sh

# Weekly backup on Sunday at 3 AM
0 3 * * 0 /usr/local/bin/mysql-backup-weekly.sh

# Monthly backup on 1st at 4 AM
0 4 1 * * /usr/local/bin/mysql-backup-monthly.sh
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
