# Upgrade MySQL 8.0 to 9.4 in Docker

**Status**: Ready to Execute  
**Last Updated**: February 14, 2026  
**Current Version**: MySQL 8.0  
**Target Version**: MySQL 9.4

---

## Overview

This guide explains how to upgrade the local MySQL Docker container from version 8.0 to 9.4. The process is straightforward since Docker makes version upgrades simple and safe.

---

## Prerequisites

- Docker and Docker Compose installed
- MySQL 8.0 running in Docker (current setup)
- Access to MySQL root password (in `backend/.env`)
- Sufficient disk space for backup (~50-100 MB)

---

## Important: Local vs Docker MySQL

### Current Setup Verification

You may have both a local MySQL installation and Docker MySQL. Here's how to check:

```powershell
# Check for local MySQL services
Get-Service | Where-Object {$_.Name -like "*mysql*" -or $_.DisplayName -like "*mysql*"}

# Check what's using port 3306
Get-NetTCPConnection -LocalPort 3306 -ErrorAction SilentlyContinue | Select-Object LocalAddress, LocalPort, State, OwningProcess

# Check the process
Get-Process -Id <OwningProcess> | Select-Object Id, ProcessName, Path
```

### Expected Results

✅ **Correct Setup** (what you should see):

- Docker MySQL running on port 3306 (process: `com.docker.backend`)
- Local MySQL80 service exists but is **Stopped**
- No conflicts

❌ **Potential Conflict** (if you see this):

- Local MySQL80 service is **Running**
- Port 3306 is used by `mysqld.exe` instead of Docker

### Data Directory Separation

**Important**: Docker MySQL and local MySQL use **separate data directories**:

- **Docker MySQL**: `./mysql_data` (in your project folder)
- **Local MySQL80**: `C:\ProgramData\MySQL\MySQL Server 8.0\Data`

These do NOT share data, so there's no risk of corruption or conflicts.

### If Local MySQL is Running

If you find your local MySQL80 service is running and you want to use Docker MySQL instead:

```powershell
# Stop local MySQL
Stop-Service MySQL80

# Disable auto-start (optional)
Set-Service MySQL80 -StartupType Disabled

# Start Docker MySQL
docker-compose up -d mysql
```

### If You Want to Remove Local MySQL

If you never use the local MySQL80 installation:

```powershell
# Option 1: Via Windows Settings
# Go to Settings > Apps > MySQL Server 8.0 > Uninstall

# Option 2: Via PowerShell (check package name first)
Get-Package -Name "MySQL*"
# Then uninstall
Get-Package -Name "MySQL Server 8.0" | Uninstall-Package
```

---

## Quick Upgrade (Recommended)

### Step 1: Backup Your Data (Critical!)

```powershell
# Create backup directory
mkdir C:\backup -Force

# Get your MySQL root password from backend/.env
# Then backup the database (replace <password> with actual password)
docker exec myAdmin-mysql-1 mysqldump -u root -p<password> --all-databases > C:\backup\mysql_backup_$(Get-Date -Format 'yyyyMMdd').sql

# Or just the finance database
docker exec myAdmin-mysql-1 mysqldump -u root -p<password> finance > C:\backup\finance_backup_$(Get-Date -Format 'yyyyMMdd').sql
```

**Important**: Don't skip this step! This is your safety net.

---

### Step 2: Stop the Containers

```powershell
docker-compose down
```

---

### Step 3: Update docker-compose.yml

Change the MySQL image version from `8.0` to `9.4`:

```yaml
services:
  mysql:
    image: mysql:9.4 # Changed from mysql:8.0
    command: --lower-case-table-names=2
    env_file:
      - ./backend/.env
    environment:
      MYSQL_DATABASE: finance
      MYSQL_USER: peter
    volumes:
      - ./mysql_data:/var/lib/mysql
    ports:
      - "3306:3306"
    mem_limit: 2g
    cpus: 1.0
    restart: unless-stopped
```

**Note**: This change has already been made in your `docker-compose.yml`.

---

### Step 4: Pull MySQL 9.4 Image and Start

```powershell
# Pull the new MySQL 9.4 image
docker-compose pull mysql

# Start the containers
docker-compose up -d

# Watch the logs to see the upgrade process
docker-compose logs -f mysql
```

MySQL 9.4 will automatically detect the MySQL 8.0 data directory and upgrade it.

---

### Step 5: Verify the Upgrade

```powershell
# Check MySQL version
docker exec -it myAdmin-mysql-1 mysql -u root -p -e "SELECT VERSION();"

# Expected output: 9.4.0

# Verify your database is intact
docker exec -it myAdmin-mysql-1 mysql -u root -p -e "USE finance; SHOW TABLES;"

# Check row counts
docker exec -it myAdmin-mysql-1 mysql -u root -p -e "USE finance; SELECT COUNT(*) FROM mutaties; SELECT COUNT(*) FROM bnb;"
```

---

### Step 6: Test Your Application

```powershell
# Check backend logs
docker-compose logs backend

# Test health endpoint
curl http://localhost:5000/api/health

# Test database connection
curl http://localhost:5000/api/status
```

---

## Alternative: Clean Upgrade

If the automatic upgrade encounters issues, use this clean installation approach:

### Step 1: Backup and Preserve Old Data

```powershell
# Backup database
docker exec myAdmin-mysql-1 mysqldump -u root -p<password> --all-databases > C:\backup\mysql_full_backup.sql

# Stop containers
docker-compose down

# Rename old data directory (keep as backup)
Rename-Item mysql_data mysql_data_8.0_backup
```

---

### Step 2: Start Fresh with MySQL 9.4

```powershell
# Start with empty data directory (will be created automatically)
docker-compose up -d mysql

# Wait for MySQL to initialize (30-60 seconds)
docker-compose logs -f mysql

# Look for: "ready for connections"
```

---

### Step 3: Restore Your Data

```powershell
# Import the backup
docker exec -i myAdmin-mysql-1 mysql -u root -p<password> < C:\backup\mysql_full_backup.sql

# Verify
docker exec -it myAdmin-mysql-1 mysql -u root -p -e "SELECT VERSION(); SHOW DATABASES; USE finance; SHOW TABLES;"
```

---

### Step 4: Start Backend

```powershell
# Start all services
docker-compose up -d

# Verify everything works
curl http://localhost:5000/api/health
```

---

## Rollback Procedure

If you encounter issues and need to rollback to MySQL 8.0:

### Option 1: Rollback with Existing Data

```powershell
# Stop containers
docker-compose down

# Change docker-compose.yml back to mysql:8.0
# Edit: image: mysql:8.0

# Start containers
docker-compose up -d
```

---

### Option 2: Rollback with Backup Data

```powershell
# Stop containers
docker-compose down

# Remove MySQL 9.4 data
Remove-Item -Recurse -Force mysql_data

# Restore MySQL 8.0 data (if you renamed it)
Rename-Item mysql_data_8.0_backup mysql_data

# Change docker-compose.yml back to mysql:8.0
# Start containers
docker-compose up -d
```

---

### Option 3: Restore from Backup

```powershell
# Stop containers
docker-compose down

# Remove current data
Remove-Item -Recurse -Force mysql_data

# Change docker-compose.yml back to mysql:8.0
# Start with empty data directory
docker-compose up -d mysql

# Wait for initialization
Start-Sleep -Seconds 30

# Restore backup
docker exec -i myAdmin-mysql-1 mysql -u root -p<password> < C:\backup\mysql_backup_YYYYMMDD.sql
```

---

## Important Notes

### MySQL 9.4 Changes

1. **Authentication**: Default authentication plugin may differ
2. **Deprecated Features**: Some MySQL 8.0 features removed
3. **Performance**: Generally improved over 8.0
4. **Compatibility**: Most applications work without changes

### Data Persistence

Your data is stored in `./mysql_data` directory which:

- ✅ Persists across container restarts
- ✅ Survives container deletion
- ✅ Can be backed up by copying the directory
- ✅ Is automatically upgraded by MySQL 9.4

### Configuration

The `--lower-case-table-names=2` setting is preserved, which is important for:

- Windows compatibility
- Case-insensitive table name matching
- Consistency with Railway MySQL

---

## Troubleshooting

### Issue: Port 3306 Already in Use

```powershell
# Check what's using port 3306
Get-NetTCPConnection -LocalPort 3306 -ErrorAction SilentlyContinue

# If local MySQL is running
Stop-Service MySQL80

# Then start Docker MySQL
docker-compose up -d mysql
```

---

### Issue: Container Won't Start

```powershell
# Check logs
docker-compose logs mysql

# Common causes:
# - Data directory corruption
# - Incompatible configuration
# - Port already in use

# Solution: Use clean upgrade approach
```

---

### Issue: "Access Denied" Errors

```powershell
# Reset root password
docker exec -it myAdmin-mysql-1 mysql -u root -p

# Or recreate user
docker exec -it myAdmin-mysql-1 mysql -u root -p -e "
  CREATE USER IF NOT EXISTS 'peter'@'%' IDENTIFIED BY '<password>';
  GRANT ALL PRIVILEGES ON finance.* TO 'peter'@'%';
  FLUSH PRIVILEGES;
"
```

---

### Issue: Backend Can't Connect

```powershell
# Check backend logs
docker-compose logs backend

# Verify MySQL is running
docker-compose ps

# Test connection manually
docker exec -it myAdmin-mysql-1 mysql -u peter -p -e "USE finance; SELECT COUNT(*) FROM mutaties;"

# Restart backend
docker-compose restart backend
```

---

### Issue: Data Missing After Upgrade

```powershell
# Stop containers
docker-compose down

# Restore from backup
docker-compose up -d mysql
Start-Sleep -Seconds 30
docker exec -i myAdmin-mysql-1 mysql -u root -p<password> < C:\backup\mysql_backup_YYYYMMDD.sql
```

---

## Verification Checklist

After upgrade, verify:

- [ ] MySQL version is 9.4.0
- [ ] All tables exist (`SHOW TABLES;`)
- [ ] Row counts match expectations
- [ ] Backend connects successfully
- [ ] Health endpoint returns 200 OK
- [ ] Can query data from frontend
- [ ] No errors in backend logs
- [ ] No errors in MySQL logs

---

## Post-Upgrade Tasks

### 1. Update Documentation

Update any documentation that references MySQL 8.0 to MySQL 9.4.

### 2. Monitor Performance

```powershell
# Check MySQL performance
docker stats myAdmin-mysql-1

# Check slow queries
docker exec -it myAdmin-mysql-1 mysql -u root -p -e "
  SELECT * FROM mysql.slow_log LIMIT 10;
"
```

### 3. Optimize Tables (Optional)

```powershell
# Optimize all tables in finance database
docker exec -it myAdmin-mysql-1 mysql -u root -p -e "
  USE finance;
  OPTIMIZE TABLE mutaties;
  OPTIMIZE TABLE bnb;
  OPTIMIZE TABLE bnbplanned;
  OPTIMIZE TABLE bnbfuture;
"
```

### 4. Clean Up Old Backups (After Verification)

```powershell
# After confirming everything works (wait a few days)
# Remove old MySQL 8.0 data directory if you renamed it
Remove-Item -Recurse -Force mysql_data_8.0_backup

# Keep at least one backup file
```

---

## Quick Reference Commands

```powershell
# Backup
docker exec myAdmin-mysql-1 mysqldump -u root -p<password> finance > C:\backup\finance.sql

# Stop
docker-compose down

# Update docker-compose.yml (change mysql:8.0 to mysql:9.4)

# Pull and start
docker-compose pull mysql
docker-compose up -d

# Verify
docker exec -it myAdmin-mysql-1 mysql -u root -p -e "SELECT VERSION();"

# Check logs
docker-compose logs mysql
docker-compose logs backend

# Test
curl http://localhost:5000/api/health
```

---

## Summary

Upgrading MySQL in Docker is straightforward:

1. **Backup** your data (critical!)
2. **Update** docker-compose.yml to use `mysql:9.4`
3. **Restart** containers with `docker-compose up -d`
4. **Verify** the upgrade worked
5. **Test** your application

The entire process takes 5-10 minutes and is reversible if needed.

---

## Support

If you encounter issues:

1. Check the logs: `docker-compose logs mysql`
2. Verify backup exists: `ls C:\backup`
3. Try the clean upgrade approach
4. Rollback if necessary

**Remember**: Always keep your backup until you're confident the upgrade is stable!
