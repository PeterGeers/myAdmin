# Environment Setup - Chart of Accounts Management

## Overview

This document explains the environment isolation between local development and production after the Railway migration.

## Environment Architecture

### Local Development (Docker Desktop)

- **Database**: Local MySQL 8.0 container (`myadmin-mysql-1`)
- **Host**: `localhost:3306`
- **Database Name**: `finance` (local copy)
- **User**: `peter`
- **Backend**: Runs in Docker container (`myadmin-backend-1`)
- **Purpose**: Safe development and testing without affecting production

### Production (Railway)

- **Database**: Railway MySQL 9.4.0
- **Host**: `shinkansen.proxy.rlwy.net:42375` (TCP proxy)
- **Database Name**: `finance` (production data)
- **User**: `root`
- **Backend**: Deployed on Railway
- **Purpose**: Live production environment

## Configuration Files

### backend/.env (Local Development)

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=<local-db-user>
DB_PASSWORD=<local-db-password>
DB_NAME=finance
TEST_MODE=false
```

### Railway Environment Variables (Production)

```env
DB_HOST=mysql.railway.internal
DB_PORT=3306
DB_USER=root
DB_PASSWORD=<railway-password>
DB_NAME=finance
```

## TEST_MODE Clarification

**Before Railway Migration:**

- `TEST_MODE=true` → Local `testfinance` database
- `TEST_MODE=false` → Local `finance` database (production)

**After Railway Migration:**

- Local development always uses local MySQL container
- `TEST_MODE` is no longer needed for environment switching
- Production is completely isolated on Railway
- Local `finance` database is a development copy, NOT production

## Ensuring Isolation

### ✓ Verified Isolation

1. **Different Hosts**: Local uses `localhost`, Production uses Railway
2. **Different Credentials**: Local uses different user credentials than Production
3. **Separate Databases**: Local MySQL container vs Railway MySQL
4. **No Cross-Contamination**: Changes in local dev do NOT affect production

### How to Verify

Run this command to check your current connection:

```bash
docker exec myadmin-backend-1 env | findstr DB_
```

Expected output for local development:

```
DB_HOST=mysql  (Docker network name, resolves to local container)
DB_USER=peter
DB_NAME=finance
```

## Development Workflow

1. **Local Development**:
   - Make changes to code
   - Test against local MySQL container
   - Data is isolated from production
   - Safe to experiment

2. **Testing**:
   - Run tests against local database
   - No risk to production data

3. **Deployment**:
   - Push code to GitHub
   - Railway auto-deploys from main branch
   - Production uses Railway MySQL

## Safety Checklist

Before starting development:

- [ ] Verify `backend/.env` has `DB_HOST=localhost`
- [ ] Verify `DB_USER=peter` (not root)
- [ ] Confirm local MySQL container is running: `docker ps`
- [ ] Test connection to local database
- [ ] Confirm NOT connected to Railway

## Summary

✓ **Local development is completely isolated from production**

- Local: Docker MySQL container on localhost
- Production: Railway MySQL in the cloud
- No way to accidentally affect production from local dev
- TEST_MODE no longer controls environment switching

---

## Quick Status Check Commands

### Check Implementation Progress

```bash
# Check if validation functions exist
grep -n "def validate_account_number" backend/src/tenant_admin_routes.py
grep -n "def validate_account_name" backend/src/tenant_admin_routes.py
grep -n "def has_fin_module" backend/src/tenant_admin_routes.py

# Check if API endpoints exist
grep -n "chart-of-accounts" backend/src/tenant_admin_routes.py

# Check frontend files
dir frontend\src\types\chartOfAccounts.ts 2>nul && echo "Types exist" || echo "Types not created yet"
dir frontend\src\services\chartOfAccountsService.ts 2>nul && echo "Service exists" || echo "Service not created yet"
dir frontend\src\pages\TenantAdmin\ChartOfAccounts.tsx 2>nul && echo "Component exists" || echo "Component not created yet"
```

### Verify Database Schema

```bash
# Connect to local MySQL and check table
docker exec -it myadmin-mysql-1 mysql -upeter -p -e "DESCRIBE finance.rekeningschema;"
```

### Check Current Git Branch

```bash
git branch --show-current
# Should show: feature/chart-of-accounts-management
```

### Run Tests (when available)

```bash
# Backend tests
cd backend
pytest tests/unit/test_chart_of_accounts.py -v
pytest tests/api/test_chart_of_accounts_api.py -v

# Frontend tests
cd frontend
npm test -- ChartOfAccounts
```
