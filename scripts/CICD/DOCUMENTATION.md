# myAdmin CI/CD Pipeline - Complete Documentation

**Version:** 1.0  
**Last Updated:** January 16, 2026

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Overview](#overview)
3. [Scripts Reference](#scripts-reference)
4. [Database Safety](#database-safety)
5. [Deployment Workflows](#deployment-workflows)
6. [Container Troubleshooting](#container-troubleshooting)
7. [Best Practices](#best-practices)
8. [Advanced Usage](#advanced-usage)

---

## Quick Start

### First Time Setup

```powershell
# 1. Build everything
.\scripts\cicd\build.ps1

# 2. Deploy
.\scripts\cicd\deploy.ps1

# 3. Verify it works
curl http://localhost:5000/api/health
```

### Regular Deployment

```powershell
# One command does it all (testing/development)
.\scripts\cicd\pipeline.ps1

# Production deployment (with confirmation prompts)
.\scripts\cicd\pipeline.ps1 -Environment production
```

### Container Issues? (Most Common Problem)

```powershell
# Step 1: Quick diagnosis
.\scripts\cicd\check-containers.ps1

# Step 2: Try automatic fix
.\scripts\cicd\check-containers.ps1 -Fix

# Step 3: Deep clean (do this BEFORE restarting laptop!)
.\scripts\cicd\deep-clean.ps1
```

### Emergency Rollback

```powershell
# List available backups
.\scripts\cicd\rollback.ps1 -ListBackups

# Rollback to latest backup
.\scripts\cicd\rollback.ps1
```

---

## Overview

This CI/CD pipeline provides a safe, automated deployment process for the myAdmin application with **critical focus on database safety**. The pipeline includes validation, testing, building, deployment, and rollback capabilities.

### Environment Modes

The pipeline supports two deployment modes:

- **Default Mode**: Faster deployment without confirmation prompts. Use for testing and development.
- **Production Mode** (`-Environment production`): Requires explicit confirmation before deployment. Use when deploying to live/production environment.

**Note:** Both modes deploy to the same Docker containers. The difference is in safety prompts and validation strictness.

### Key Features

✅ **Database Protection**

- Automatic backup before every deployment
- Backup verification (size check)
- Keeps last 10 backups automatically
- Quick rollback capability

✅ **Validation & Testing**

- ESLint for frontend code quality
- Flake8 for Python code quality
- Automated test execution
- Build artifact verification

✅ **Health Checks**

- Backend API health endpoint
- Database connectivity tests
- Service status verification
- Auto-rollback on failure

✅ **Container Management**

- Automatic container health checks
- Deep clean and recovery
- Docker Desktop restart capability

✅ **Comprehensive Logging**

- All operations logged with timestamps
- Separate logs for each run
- Easy troubleshooting

---

## Scripts Reference

### 1. build.ps1 - Build and Validation

Validates and builds both frontend and backend components.

**Usage:**

```powershell
# Standard build with tests
.\scripts\cicd\build.ps1

# Skip tests (faster, not recommended for production)
.\scripts\cicd\build.ps1 -SkipTests

# Verbose output
.\scripts\cicd\build.ps1 -Verbose
```

**What it does:**

- ✅ Validates environment and dependencies
- ✅ Installs frontend dependencies (npm ci)
- ✅ Runs ESLint on frontend code
- ✅ Runs frontend tests with coverage
- ✅ Builds production frontend bundle
- ✅ Validates backend Python environment
- ✅ Runs flake8 linting on backend
- ✅ Runs backend pytest tests
- ✅ Builds Docker images

**Output:** Build logs in `scripts/cicd/logs/build-*.log`

---

### 2. deploy.ps1 - Safe Deployment with Database Protection

Deploys the application with comprehensive safety checks and database backup.

**Usage:**

```powershell
# Deploy with default settings (no confirmation prompts)
.\scripts\cicd\deploy.ps1

# Deploy with production safety (requires confirmation prompts)
.\scripts\cicd\deploy.ps1 -Environment production

# Skip database backup (NOT RECOMMENDED)
.\scripts\cicd\deploy.ps1 -SkipBackup

# Skip smoke tests
.\scripts\cicd\deploy.ps1 -SkipSmokeTests

# Force deployment without prompts
.\scripts\cicd\deploy.ps1 -Environment production -Force
```

**What it does:**

**Step 0: Pre-flight Container Check**

- Verifies Docker is running
- Checks existing container health
- Cleans up problematic containers

**Step 1: Pre-deployment Validation**

- Checks for required files
- Validates build artifacts exist
- Warns if production containers are running

**Step 2: 🔒 CRITICAL - Database Backup**

- Creates full MySQL dump before any changes
- Verifies backup file integrity
- Stores in `scripts/cicd/backups/`
- Keeps last 10 backups automatically

**Step 3: Graceful Service Shutdown**

- Stops containers gracefully
- Falls back to force stop if needed

**Step 4: Deployment**

- Starts services with docker-compose
- Verifies containers are running
- Captures logs if startup fails

**Step 5: Health Checks**

- Tests backend API health endpoint
- Retries up to 12 times (60 seconds)
- Rolls back if health checks fail

**Step 6: Database Connection Test**

- Verifies MySQL is accessible
- Tests database queries

**Step 7: Smoke Tests**

- Frontend accessibility test
- API endpoint test
- Database query test

**Output:**

- Deployment logs in `scripts/cicd/logs/deploy-*.log`
- Database backups in `scripts/cicd/backups/mysql-backup-*.sql`

---

### 3. pipeline.ps1 - Complete CI/CD Pipeline

Runs the full pipeline: git → build → deploy → verify

**Usage:**

```powershell
# Run full pipeline (default mode)
.\scripts\cicd\pipeline.ps1

# Run full pipeline for production
.\scripts\cicd\pipeline.ps1 -Environment production

# With custom commit message
.\scripts\cicd\pipeline.ps1 -CommitMessage "Feature: Added new report"

# With git tag (for releases)
.\scripts\cicd\pipeline.ps1 -Environment production -Tag "v1.2.0"

# Skip git operations
.\scripts\cicd\pipeline.ps1 -SkipGit

# Skip tests (faster, not recommended)
.\scripts\cicd\pipeline.ps1 -SkipTests

# Skip database backup (NOT RECOMMENDED)
.\scripts\cicd\pipeline.ps1 -SkipBackup

# Force without prompts (commits and deploys automatically)
.\scripts\cicd\pipeline.ps1 -Environment production -Force
```

**Pipeline Stages:**

0. **GIT** - Commits changes and optionally creates tags
1. **BUILD** - Validates, tests, and builds application
2. **DEPLOY** - Safely deploys with database backup
3. **VERIFY** - Post-deployment verification and health checks

**Git Operations (Stage 0):**

- Checks for uncommitted changes
- Shows what will be committed
- Prompts for commit confirmation (unless -Force)
- Commits with automatic or custom message
- Optionally creates git tags
- Optionally pushes to remote
- Can be skipped with -SkipGit flag

**Default Commit Messages:**

- Production: "Production deployment YYYY-MM-DD HH:mm"
- Default: "Deployment YYYY-MM-DD HH:mm"

**Output:** Pipeline logs in `scripts/cicd/logs/pipeline-*.log`

---

### 4. rollback.ps1 - Database Rollback

Restores database from a previous backup.

**Usage:**

```powershell
# List available backups
.\scripts\cicd\rollback.ps1 -ListBackups

# Rollback to latest backup (requires confirmation)
.\scripts\cicd\rollback.ps1

# Rollback to specific backup
.\scripts\cicd\rollback.ps1 -BackupFile "scripts/cicd/backups/mysql-backup-20260116-143022.sql"

# Force rollback without confirmation (DANGEROUS)
.\scripts\cicd\rollback.ps1 -Force
```

**What it does:**

- Lists available database backups
- Prompts for confirmation (type 'ROLLBACK')
- Restores MySQL database from backup file
- Verifies restoration success

**⚠️ WARNING:** This will replace current database data with backup data!

**Output:** Rollback logs in `scripts/cicd/logs/rollback-*.log`

---

### 5. check-containers.ps1 - Container Health Check

Diagnoses container problems and provides detailed diagnostics.

**Usage:**

```powershell
# Check container health
.\scripts\cicd\check-containers.ps1

# Check and attempt automatic fix
.\scripts\cicd\check-containers.ps1 -Fix

# Verbose output
.\scripts\cicd\check-containers.ps1 -Verbose
```

**What it checks:**

- ✓ Is Docker daemon running?
- ✓ Are containers running?
- ✓ Is backend responding to health checks?
- ✓ Is MySQL accessible?
- ✓ Any orphaned containers?
- ✓ Disk space sufficient?
- ✓ Docker resources available?

**Output:** Console output with color-coded status

---

### 6. deep-clean.ps1 - Deep Clean and Recovery

Use this when containers won't start properly and before restarting your laptop.

**Usage:**

```powershell
# Deep clean (keeps database data)
.\scripts\cicd\deep-clean.ps1

# Deep clean without data (DELETES DATABASE!)
.\scripts\cicd\deep-clean.ps1 -KeepData:$false

# Force without confirmation
.\scripts\cicd\deep-clean.ps1 -Force
```

**What it does:**

1. Stops all containers
2. Removes all containers
3. Cleans up Docker networks
4. Removes dangling images
5. Cleans build cache
6. **Restarts Docker Desktop**
7. Rebuilds images from scratch
8. Starts fresh containers
9. Runs health checks

**Time:** 2-3 minutes (vs 5-10 minutes for laptop restart)

**⚠️ Important:** By default, this preserves your database data. Use `-KeepData:$false` only if you want to delete everything.

---

## Database Safety

### 🔒 Critical Database Protection

1. **Automatic Backups**

   - Full database dump before every deployment
   - Backup verification (size check)
   - Automatic retention (keeps last 10 backups)

2. **Backup Location**

   - `scripts/cicd/backups/mysql-backup-YYYYMMDD-HHMMSS.sql`

3. **Rollback Capability**

   - Quick restoration from any backup
   - Confirmation required to prevent accidents

4. **Data Integrity Checks**
   - Database connection tests
   - Query execution tests
   - Health check verification

### Manual Database Backup

```powershell
# Create manual backup
.\scripts\containers\backup-database.ps1
```

### Viewing Backups

```powershell
# List all backups with details
.\scripts\cicd\rollback.ps1 -ListBackups

# View backup files
Get-ChildItem scripts\cicd\backups
```

---

## Deployment Workflows

### Quick Deployment (Testing/Development)

```powershell
# Fast deployment without confirmation prompts
.\scripts\cicd\pipeline.ps1
```

**Use when:**

- Testing changes during development
- Deploying to local environment
- Quick iterations

### Safe Deployment (Production/Live)

```powershell
# Deployment with confirmation prompts and extra safety
.\scripts\cicd\pipeline.ps1 -Environment production
```

**Use when:**

- Deploying to production
- Working with live data
- Want extra confirmation before changes

### Build Only (No Deployment)

```powershell
# Build and test without deploying
.\scripts\cicd\build.ps1
```

**Use when:**

- Testing build process
- Running CI checks
- Validating code before deployment

### Emergency Rollback

```powershell
# List backups
.\scripts\cicd\rollback.ps1 -ListBackups

# Rollback to latest
.\scripts\cicd\rollback.ps1

# Rollback to specific backup
.\scripts\cicd\rollback.ps1 -BackupFile "scripts/cicd/backups/mysql-backup-20260116-143022.sql"
```

**Use when:**

- Bad deployment
- Data corruption
- Need to restore previous state

---

## Container Troubleshooting

### 🔧 When Containers Won't Start or Work Properly

This is the most common issue with Docker on Windows. Follow this escalation path:

### Recovery Steps (In Order)

#### 🟢 Level 1: Quick Fix (Try First)

**Time: 30 seconds**

```powershell
.\scripts\cicd\check-containers.ps1 -Fix
```

**What it does:**

- Stops containers
- Restarts containers
- Re-checks health

**When to use:** First attempt at fixing issues

---

#### 🟡 Level 2: Deep Clean (Before Laptop Restart!)

**Time: 2-3 minutes**

```powershell
.\scripts\cicd\deep-clean.ps1
```

**What it does:**

- Stops all containers
- Removes all containers
- Cleans Docker networks
- Removes dangling images
- **Restarts Docker Desktop**
- Rebuilds images
- Starts fresh containers
- ✅ **Keeps your database data safe**

**When to use:**

- Quick fix didn't work
- Docker feels "stuck"
- Before you restart your laptop

**Why this works:**
Docker Desktop on Windows sometimes gets into a bad state. Restarting it programmatically often fixes issues without needing a full laptop restart.

---

#### 🔴 Level 3: Deep Clean + Data Reset (Nuclear Option)

**Time: 2-3 minutes**

```powershell
.\scripts\cicd\deep-clean.ps1 -KeepData:$false
```

**⚠️ WARNING:** This deletes your database data!

**What it does:**

- Everything from Level 2
- **PLUS: Deletes all Docker volumes (including database)**

**When to use:**

- Database is corrupted
- You want a completely fresh start
- You have a backup

**Before running:**

```powershell
# Create backup first!
.\scripts\cicd\rollback.ps1 -ListBackups
```

---

#### 🔴 Level 4: Laptop Restart (Last Resort)

**Time: 5-10 minutes**

1. Restart your laptop
2. Wait for Windows to fully start
3. Wait for Docker Desktop to start (check system tray)
4. Open PowerShell and run:

```powershell
docker-compose up -d
```

**When to use:**

- Deep clean didn't work
- Docker Desktop won't start
- System feels sluggish

---

### Common Scenarios

#### Scenario 1: "Backend not responding"

```powershell
# Check backend logs
docker-compose logs backend

# If logs show errors, try deep clean
.\scripts\cicd\deep-clean.ps1
```

#### Scenario 2: "MySQL won't start"

```powershell
# Check MySQL logs
docker-compose logs mysql

# Check disk space
.\scripts\cicd\check-containers.ps1

# Try deep clean
.\scripts\cicd\deep-clean.ps1
```

#### Scenario 3: "Containers keep restarting"

```powershell
# Check status
docker-compose ps

# View logs
docker-compose logs -f

# Deep clean usually fixes this
.\scripts\cicd\deep-clean.ps1
```

#### Scenario 4: "Docker Desktop won't start"

1. Open Task Manager (Ctrl+Shift+Esc)
2. End all Docker processes
3. Restart Docker Desktop manually
4. If still not working, restart laptop

#### Scenario 5: "Everything was working, now it's not"

```powershell
# This is the most common issue - try deep clean first
.\scripts\cicd\deep-clean.ps1
```

---

### Quick Reference Table

| Problem                | Solution                     | Command                                          |
| ---------------------- | ---------------------------- | ------------------------------------------------ |
| Containers won't start | Deep clean                   | `.\scripts\cicd\deep-clean.ps1`                  |
| Backend not responding | Check logs + deep clean      | `docker-compose logs backend`                    |
| MySQL issues           | Deep clean                   | `.\scripts\cicd\deep-clean.ps1`                  |
| Docker Desktop stuck   | Deep clean (restarts Docker) | `.\scripts\cicd\deep-clean.ps1`                  |
| Everything broken      | Laptop restart               | Restart → `docker-compose up -d`                 |
| Need fresh start       | Deep clean without data      | `.\scripts\cicd\deep-clean.ps1 -KeepData:$false` |

---

### Prevention Tips

#### 1. Regular Cleanup

```powershell
# Run this weekly to prevent issues
docker system prune -f
```

#### 2. Monitor Disk Space

```powershell
# Check disk space
.\scripts\cicd\check-containers.ps1
```

Docker needs at least 5GB free space to work properly.

#### 3. Restart Docker Desktop Weekly

Close and restart Docker Desktop once a week to prevent issues.

#### 4. Keep Docker Desktop Updated

Check for updates in Docker Desktop settings.

---

## Best Practices

### Pre-Deployment Checklist

- [ ] All tests passing locally
- [ ] Code reviewed and approved
- [ ] Environment variables configured in `backend/.env`
- [ ] Docker Desktop running
- [ ] Database backup strategy confirmed
- [ ] Run build script: `.\scripts\cicd\build.ps1`
- [ ] Test in default mode first

### Deployment Safety

1. **Always backup before production deployment**
2. **Test in default mode first**
3. **Review logs after deployment**
4. **Keep backups for at least 7 days**
5. **Never skip tests for production**
6. **Monitor application health after deployment**
7. **Have rollback plan ready**

### Container Management

1. **Check container health regularly**

   ```powershell
   .\scripts\cicd\check-containers.ps1
   ```

2. **Use deep-clean before laptop restart**

   ```powershell
   .\scripts\cicd\deep-clean.ps1
   ```

3. **Monitor disk space**

   - Keep at least 5GB free
   - Run `docker system prune -f` weekly

4. **Restart Docker Desktop weekly**
   - Prevents issues from accumulating

---

## Advanced Usage

### Custom Build Options

```powershell
# Build with specific options
.\scripts\cicd\build.ps1 -SkipTests -Verbose
```

### Deployment with Custom Settings

```powershell
# Production deployment, skip backup (not recommended)
.\scripts\cicd\deploy.ps1 -Environment production -SkipBackup -Force
```

### Pipeline with All Options

```powershell
# Fast pipeline for testing
.\scripts\cicd\pipeline.ps1 -SkipTests -Force
```

### Backup Management

```powershell
# List backups
.\scripts\cicd\rollback.ps1 -ListBackups

# View backup details
Get-ChildItem scripts\cicd\backups | Sort-Object LastWriteTime -Descending

# Delete old backups (keeps last 10 automatically)
Get-ChildItem scripts\cicd\backups -Filter "mysql-backup-*.sql" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 10 |
    Remove-Item -Force
```

### Monitoring After Deployment

```powershell
# Check service status
docker-compose ps

# View logs (all services)
docker-compose logs -f

# View logs (specific service)
docker-compose logs -f backend
docker-compose logs -f mysql

# Test health endpoint
curl http://localhost:5000/api/health

# View latest deployment log
Get-ChildItem scripts/cicd/logs |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1 |
    Get-Content
```

---

## File Locations

```
scripts/cicd/
├── build.ps1                  # Build script
├── deploy.ps1                 # Deployment script
├── pipeline.ps1               # Full pipeline
├── rollback.ps1               # Database rollback
├── check-containers.ps1       # Container diagnostics
├── deep-clean.ps1             # Deep clean and recovery
├── DOCUMENTATION.md           # This file
├── logs/                      # All operation logs
│   ├── build-*.log
│   ├── deploy-*.log
│   ├── pipeline-*.log
│   └── rollback-*.log
└── backups/                   # Database backups
    └── mysql-backup-*.sql
```

---

## Environment Variables

Required in `backend/.env`:

- `MYSQL_ROOT_PASSWORD` - For database backup/restore
- `MYSQL_PASSWORD` - For application database access
- `DB_NAME` - Database name

---

## Getting Help

### When Asking for Help, Provide:

1. **Container diagnostics:**

```powershell
.\scripts\cicd\check-containers.ps1
```

2. **Container logs:**

```powershell
docker-compose logs
```

3. **Docker version:**

```powershell
docker --version
docker-compose --version
```

4. **Recent operation logs:**

```powershell
Get-ChildItem scripts/cicd/logs | Sort-Object LastWriteTime -Descending | Select-Object -First 3
```

5. **What you tried and what happened**

---

## Application URLs

After successful deployment:

- **Frontend:** http://localhost:5000
- **Backend API:** http://localhost:5000/api
- **Health Check:** http://localhost:5000/api/health
- **MySQL:** localhost:3306

---

## Version History

- **1.0** (January 16, 2026) - Initial release
  - Build, deploy, and pipeline scripts
  - Database backup and rollback
  - Container health checks and diagnostics
  - Deep clean and recovery
  - Comprehensive documentation

---

**For quick reference, see the command cheat sheet below:**

## Command Cheat Sheet

```powershell
# Build
.\scripts\cicd\build.ps1

# Deploy (default)
.\scripts\cicd\pipeline.ps1

# Deploy (production)
.\scripts\cicd\pipeline.ps1 -Environment production

# Check containers
.\scripts\cicd\check-containers.ps1

# Fix containers (quick)
.\scripts\cicd\check-containers.ps1 -Fix

# Fix containers (deep clean)
.\scripts\cicd\deep-clean.ps1

# Rollback database
.\scripts\cicd\rollback.ps1 -ListBackups
.\scripts\cicd\rollback.ps1

# View logs
docker-compose logs -f

# Check status
docker-compose ps
```

---

## Git Integration

### Automatic Git Operations

The pipeline automatically handles git operations before building and deploying:

**What it does:**

1. Checks for uncommitted changes
2. Shows what will be committed
3. Prompts for confirmation (unless -Force)
4. Commits with automatic or custom message
5. Optionally creates git tags
6. Optionally pushes to remote

### Usage Examples

#### Basic Deployment with Auto-Commit

```powershell
# Pipeline will prompt to commit changes
.\scripts\cicd\pipeline.ps1
```

#### Custom Commit Message

```powershell
# Specify your own commit message
.\scripts\cicd\pipeline.ps1 -CommitMessage "Feature: Added invoice export"
```

#### Production Release with Tag

```powershell
# Create a tagged release
.\scripts\cicd\pipeline.ps1 -Environment production -Tag "v1.2.0"

# This will:
# 1. Commit changes with message "Production deployment 2026-01-16 14:30"
# 2. Create tag v1.2.0
# 3. Prompt to push to remote
# 4. Build and deploy
```

#### Skip Git Operations

```powershell
# If you've already committed manually
.\scripts\cicd\pipeline.ps1 -SkipGit
```

#### Force Mode (No Prompts)

```powershell
# Automatically commit and deploy without prompts
.\scripts\cicd\pipeline.ps1 -Force -CommitMessage "Hotfix: Fixed critical bug"
```

### Git Workflow Integration

#### Feature Development

```powershell
# Work on feature
# ... make changes ...

# Deploy and test
.\scripts\cicd\pipeline.ps1 -CommitMessage "Feature: New dashboard widget"
```

#### Production Release

```powershell
# Create tagged production release
.\scripts\cicd\pipeline.ps1 -Environment production -Tag "v1.3.0" -CommitMessage "Release v1.3.0: Added reporting features"
```

#### Hotfix

```powershell
# Quick hotfix deployment
.\scripts\cicd\pipeline.ps1 -Environment production -Force -CommitMessage "Hotfix: Fixed login issue"
```

### Default Commit Messages

If you don't specify a commit message, the pipeline uses:

- **Production:** `"Production deployment YYYY-MM-DD HH:mm"`
- **Default:** `"Deployment YYYY-MM-DD HH:mm"`

### Git Tag Management

Tags are useful for tracking releases:

```powershell
# Create release tag
.\scripts\cicd\pipeline.ps1 -Environment production -Tag "v1.0.0"

# View all tags
git tag -l

# View tag details
git show v1.0.0

# Delete tag (if needed)
git tag -d v1.0.0
git push origin :refs/tags/v1.0.0
```

### Push to Remote

The pipeline will prompt you to push to remote after committing:

```
Push to remote? (yes/no)
```

- Type `yes` to push commits and tags
- Type `no` to keep changes local

In `-Force` mode, changes are committed but NOT automatically pushed.

---

## Updated Command Reference

```powershell
# === Git + Build + Deploy ===

# Standard deployment (prompts for git commit)
.\scripts\cicd\pipeline.ps1

# Production deployment with tag
.\scripts\cicd\pipeline.ps1 -Environment production -Tag "v1.2.0"

# Custom commit message
.\scripts\cicd\pipeline.ps1 -CommitMessage "Feature: Added new report"

# Skip git operations
.\scripts\cicd\pipeline.ps1 -SkipGit

# Force mode (auto-commit, no prompts)
.\scripts\cicd\pipeline.ps1 -Force

# === Build Only ===

# Build without deploying
.\scripts\cicd\build.ps1

# === Deploy Only ===

# Deploy (assumes already built)
.\scripts\cicd\deploy.ps1

# === Container Management ===

# Check container health
.\scripts\cicd\check-containers.ps1

# Fix containers (quick)
.\scripts\cicd\check-containers.ps1 -Fix

# Deep clean (restarts Docker Desktop)
.\scripts\cicd\deep-clean.ps1

# === Database Management ===

# List backups
.\scripts\cicd\rollback.ps1 -ListBackups

# Rollback to latest
.\scripts\cicd\rollback.ps1

# === Monitoring ===

# View logs
docker-compose logs -f

# Check status
docker-compose ps

# Test health
curl http://localhost:5000/api/health
```
