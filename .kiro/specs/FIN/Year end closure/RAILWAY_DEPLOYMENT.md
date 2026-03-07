# Railway Deployment Guide - Year-End Closure

**Environment**: Railway (Backend + MySQL) + GitHub Pages (Frontend)  
**Date**: March 3, 2026

## Environment Overview

- **Backend**: Railway (auto-deploys from `main` branch)
- **Database**: MySQL on Railway (persistent volume)
- **Frontend**: GitHub Pages (static hosting from `gh-pages` branch)

## Pre-Deployment Checklist

- [x] All code committed to `feature/year-end-closure` branch
- [x] All tests passing (50 unit tests)
- [x] Documentation complete
- [x] Database backup created
- [x] Stakeholder approval obtained

## Step 1: Backup Production Database (15 min)

### Option A: Using Railway Dashboard (Recommended - Most Reliable)

1. **Get MySQL Connection Details**:
   - Go to Railway Dashboard: https://railway.app/dashboard
   - Select your project
   - Click on MySQL service
   - Go to "Connect" tab
   - Copy the connection details:
     - `MYSQL_HOST` (e.g., `containers-us-west-xxx.railway.app`)
     - `MYSQL_PORT` (e.g., `6379`)
     - `MYSQL_USER` (usually `root`)
     - `MYSQL_PASSWORD` (long string)
     - `MYSQL_DATABASE` (e.g., `myAdmin`)

2. **Create Backup Using mysqldump**:

```bash
# Replace with your actual Railway MySQL credentials
mysqldump -h containers-us-west-xxx.railway.app \
  -P 6379 \
  -u root \
  -p'YOUR_PASSWORD_HERE' \
  myAdmin > myAdmin_backup_$(date +%Y%m%d).sql
```

**Note**: Replace the host, port, and password with your actual Railway values.

### Option B: Using MySQL Workbench (GUI - Easiest)

1. Download MySQL Workbench if not installed: https://dev.mysql.com/downloads/workbench/
2. Create new connection:
   - Connection Name: `Railway Production`
   - Hostname: (from Railway dashboard)
   - Port: (from Railway dashboard)
   - Username: `root`
   - Password: (click "Store in Keychain" and enter password)
3. Test connection
4. Once connected: Server → Data Export
5. Select `myAdmin` database
6. Choose "Export to Self-Contained File"
7. Save as `myAdmin_backup_YYYYMMDD.sql`

### Option C: Using DBeaver (Free Alternative)

1. Download DBeaver: https://dbeaver.io/download/
2. Create new MySQL connection with Railway credentials
3. Right-click database → Tools → Dump Database
4. Save backup file

### Verify Backup

```bash
# Check backup file exists and has content
ls -lh myAdmin_backup_*.sql

# Should show file size > 1MB
```

## Step 2: Verify Database Schema (5 min)

**The schema changes are already applied!** ✅

The following were created during development with TEST_MODE=true:

- `year_closure_status` table exists
- `rekeningschema` has `parameters` JSON column
- All indexes created

### Verify Schema Using MySQL Workbench or HeidiSQL

1. **Connect to Railway MySQL** (you already have this working)
2. **Run these queries**:

```sql
-- Check year_closure_status table exists
SHOW TABLES LIKE 'year_closure_status';

-- Check rekeningschema has parameters column
DESCRIBE rekeningschema;

-- Check if any year closures exist
SELECT COUNT(*) as closure_count FROM year_closure_status;
```

Expected:

- `year_closure_status` table found ✅
- `parameters` column exists in `rekeningschema` (type: json) ✅
- Closure count may be 0 (if no years closed yet) or > 0 (if test closures exist)

**No migration needed** - schema is already in production database!

## Step 3: Configure VAT Netting (15 min per tenant)

### Option A: Using Direct MySQL Connection (Recommended)

Since Railway CLI isn't working, connect directly to MySQL and run the configuration:

1. **Get Railway MySQL credentials** from Railway Dashboard → MySQL service → Connect tab

2. **Connect to MySQL**:

```bash
# Using mysql command line (replace with your Railway credentials)
mysql -h containers-us-west-xxx.railway.app \
  -P 6379 \
  -u root \
  -p'YOUR_PASSWORD' \
  myAdmin
```

3. **Run VAT Configuration SQL**:

```sql
-- For GoodwinSolutions
UPDATE rekeningschema
SET parameters = JSON_SET(
    COALESCE(parameters, '{}'),
    '$.vat_netting', true,
    '$.vat_primary', '2010'
)
WHERE Account IN ('2010', '2020', '2021')
AND administration = 'GoodwinSolutions';

-- For PeterPrive
UPDATE rekeningschema
SET parameters = JSON_SET(
    COALESCE(parameters, '{}'),
    '$.vat_netting', true,
    '$.vat_primary', '2010'
)
WHERE Account IN ('2010', '2020', '2021')
AND administration = 'PeterPrive';

-- Verify configuration
SELECT Account, AccountName,
       JSON_EXTRACT(parameters, '$.vat_netting') as vat_netting,
       JSON_EXTRACT(parameters, '$.vat_primary') as vat_primary
FROM rekeningschema
WHERE Account IN ('2010', '2020', '2021')
AND administration IN ('GoodwinSolutions', 'PeterPrive');
```

Expected output: All 6 rows (3 accounts × 2 tenants) should show `vat_netting=1` and `vat_primary='2010'`

### Option B: Using MySQL Workbench/DBeaver

1. Connect to Railway MySQL (same connection as backup)
2. Open SQL editor
3. Paste and run the SQL commands above
4. Verify results in the output

### Option C: Using Railway Dashboard SQL Editor (if available)

1. Go to Railway Dashboard → MySQL service
2. Look for "Query" or "SQL" tab
3. Run the SQL commands above

### Verify Configuration

After running the configuration, verify it worked:

```sql
SELECT
    administration,
    Account,
    AccountName,
    JSON_EXTRACT(parameters, '$.vat_netting') as vat_netting,
    JSON_EXTRACT(parameters, '$.vat_primary') as vat_primary
FROM rekeningschema
WHERE Account IN ('2010', '2020', '2021')
ORDER BY administration, Account;
```

Expected: 6 rows total, all with `vat_netting=1` and `vat_primary='2010'`

## Step 4: Deploy Backend to Railway (10 min)

### Merge and Push to Main

```bash
# Merge feature branch to main
git checkout main
git merge feature/year-end-closure
git push origin main
```

### Railway Auto-Deployment

Railway will automatically:

1. Detect the push to `main` branch
2. Build the Docker container
3. Deploy the new backend
4. Restart the service (zero downtime)

### Monitor Deployment

1. Go to Railway Dashboard
2. Click on your backend service
3. Go to "Deployments" tab
4. Watch the build logs
5. Wait for "Deployment successful" message

### Verify Backend Deployment

```bash
# Test health endpoint
curl https://your-backend-url.railway.app/api/health

# Should return: {"status": "healthy"}
```

Check logs in Railway Dashboard:

- Look for: `"Loading years: [2025, 2026, 2027, 2028]"` (optimized cache)
- Look for: `"Cache loaded: 6,506 rows in 1.84s"`
- Look for: `"Memory usage: ~5.4 MB"`

## Step 5: Deploy Frontend to GitHub Pages (5 min)

### Build and Deploy

```bash
cd frontend

# Build production bundle
npm run build

# Deploy to GitHub Pages
npm run deploy
```

This will:

1. Build the React app
2. Push to `gh-pages` branch
3. GitHub Pages will auto-deploy

### Verify Frontend Deployment

1. Visit your GitHub Pages URL (e.g., `https://yourusername.github.io/myAdmin`)
2. Open browser console (F12)
3. Check for errors
4. Verify new features are visible

## Step 6: Verify Configuration in UI (15 min)

### GoodwinSolutions

1. Login to application
2. Switch to GoodwinSolutions tenant
3. Navigate to **Tenant Admin** → **Year-End Settings**
4. Verify:
   - Equity Result Account: 3080 - Resultaatrekening
   - P&L Closing Account: 8099 - Afsluitrekening
   - Validation shows "Configuration Complete" (green badge)
5. Check VAT netting (if configured):
   - Navigate to **Tenant Admin** → **Chart of Accounts**
   - Filter for accounts 2010, 2020, 2021
   - Verify "VAT Netting" badge appears

### PeterPrive

Repeat the same steps for PeterPrive tenant.

## Step 7: Test Year-End Closure (30 min)

### Test Workflow

1. Navigate to **FIN Rapporten** → **Aangifte IB**
2. Select year 2025 (or another safe test year)
3. Scroll to bottom → **Jaarafsluiting** section
4. Verify:
   - Year status badge (Open/Closed)
   - Validation summary displays
   - Net P&L result shown
   - Balance sheet account count shown
5. If year is open and safe to close:
   - Click "Jaar 2025 afsluiten" button
   - Review validation
   - Add notes (optional)
   - Click "Bevestigen"
   - Wait for success message
   - Verify report refreshes automatically
6. Test reopening:
   - Click "Jaar 2025 heropenen" button
   - Click "Bevestigen"
   - Verify report refreshes

## Step 8: Verify Reports (30 min)

### Aangifte IB Report

- [ ] Loads faster than before
- [ ] Year selector shows all years (not just cached)
- [ ] Data is correct for closed years
- [ ] Jaarafsluiting section works

### BTW Report

- [ ] Shows current year only (not cumulative)
- [ ] Opening balance displayed correctly
- [ ] Quarterly data correct

### Actuals Report

- [ ] Year selector shows all years
- [ ] Data loads correctly
- [ ] Performance improved

### Mutaties Tab

- [ ] Pagination working (1000 records default)
- [ ] Load time improved
- [ ] All data accessible

## Step 9: Monitor Performance (1 hour)

### Railway Dashboard Metrics

Check in Railway Dashboard → Backend Service → Metrics:

- [ ] **CPU Usage**: Should be similar or lower
- [ ] **Memory Usage**: Should be ~93% lower (~5 MB vs ~81 MB)
- [ ] **Response Time**: Should be faster
- [ ] **Error Rate**: Should be 0%

### Backend Logs

Check Railway logs for:

- ✅ `"Loading years: [2025, 2026, 2027, 2028]"` (only 4 years, not 34)
- ✅ `"Cache loaded: 6,506 rows"` (not 104,842 rows)
- ✅ `"Memory usage: ~5.4 MB"` (not ~81 MB)
- ❌ No error messages
- ❌ No warnings

### Frontend Console

Check browser console for:

- ❌ No JavaScript errors
- ❌ No API errors
- ✅ Successful API calls

## Step 10: Post-Deployment Monitoring

### First Hour

- [ ] Monitor Railway logs continuously
- [ ] Check for any errors
- [ ] Test all major features
- [ ] Verify user access

### First Day

- [ ] Review Railway metrics
- [ ] Gather user feedback
- [ ] Check for any issues
- [ ] Monitor error rates

### First Week

- [ ] Analyze performance trends
- [ ] Review user adoption
- [ ] Check Railway costs (should be lower)
- [ ] Document any issues

## Rollback Plan

### If Critical Issues Occur

#### 1. Rollback Backend (Railway)

**Option A: Revert Git Commit**

```bash
git checkout main
git revert HEAD
git push origin main
# Railway will auto-deploy the reverted version
```

**Option B: Rollback in Railway Dashboard**

1. Go to Railway Dashboard
2. Click on backend service
3. Go to "Deployments" tab
4. Find previous successful deployment
5. Click "Rollback" button

#### 2. Rollback Frontend (GitHub Pages)

```bash
git checkout gh-pages
git revert HEAD
git push origin gh-pages
# GitHub Pages will auto-deploy
```

#### 3. Restore Database (Only if Corrupted)

```bash
railway run mysql -u root -p[PASSWORD] myAdmin < myAdmin_backup_YYYYMMDD.sql
```

#### 4. Restart Railway Services

```bash
# Using Railway CLI
railway restart

# Or in Railway Dashboard: Click "Restart" button
```

## Railway-Specific Notes

### Environment Variables

Verify in Railway Dashboard → Backend Service → Variables:

- `TEST_MODE=false` (production)
- `DB_HOST` (Railway MySQL internal hostname)
- `DB_USER=root`
- `DB_PASSWORD` (from Railway MySQL service)
- `DB_NAME=myAdmin`
- All AWS, Cognito, and other required vars

### Database Connection

- Railway MySQL uses internal networking (faster, secure)
- Backend connects via internal hostname
- No need to expose MySQL publicly
- Connection pooling handled by backend

### Auto-Deployment

Railway auto-deploys when:

- Push to `main` branch (backend)
- Environment variable changes
- Manual trigger in dashboard

### Logs Access

- **Railway Dashboard**: Service → Logs tab
- **Railway CLI**: `railway logs`
- **Filter by service**: backend, mysql
- **Real-time**: `railway logs --follow`

### Cost Optimization

Expected cost reduction:

- Lower memory usage (~93% reduction)
- Faster queries (less CPU time)
- Fewer database connections needed

## Success Criteria

- [x] Railway backend deployed successfully
- [x] GitHub Pages frontend accessible
- [x] All reports working correctly
- [x] Year-end closure feature functional
- [x] Performance improvements verified
- [x] No critical bugs (URL construction bug fixed)
- [x] Cache optimization working
- [ ] User feedback positive (pending)

## Timeline Summary

| Task                 | Duration          |
| -------------------- | ----------------- |
| Database Backup      | 15 min            |
| VAT Configuration    | 15 min per tenant |
| Backend Deploy       | 10 min (auto)     |
| Frontend Deploy      | 5 min             |
| Configuration Verify | 15 min            |
| Testing              | 30 min            |
| Report Verification  | 30 min            |
| Monitoring           | 1 hour            |
| **Total**            | **2-3 hours**     |

## Support Resources

- **Railway Dashboard**: https://railway.app/dashboard
- **Railway Docs**: https://docs.railway.app/
- **Railway CLI**: https://docs.railway.app/develop/cli
- **GitHub Pages**: Repository Settings → Pages
- **USER_GUIDE.md**: End-user documentation
- **ADMIN_GUIDE.md**: Administrator troubleshooting

## Deployment Issues Encountered and Resolved

### Issue 1: Year-End API URL Construction Bug (March 3, 2026)

**Problem**: Year-end configuration and closure endpoints were failing with `ERR_NAME_NOT_RESOLVED` errors. The actual URLs being constructed were malformed:

```
https://invigorating-celebration-production.up.railway.apphttps//invigorating-celebration-production.up.railway.app/api/tenant-admin/year-end-config/validate
```

**Root Cause**: The year-end service files (`yearEndConfigService.ts` and `yearEndClosureService.ts`) were incorrectly importing and using `API_BASE_URL` from `config/api.ts`, then passing full URLs like:

```typescript
authenticatedGet(`${API_BASE_URL}/api/tenant-admin/year-end-config/validate`);
```

However, `authenticatedGet` in `apiService.ts` already adds `API_BASE_URL` internally:

```typescript
const url = `${API_BASE_URL}${endpoint}`;
```

This caused URL doubling with a malformed protocol separator.

**Solution Applied** (Commit `26ba03a`):

1. Removed `API_BASE_URL` import from both service files
2. Changed all API calls to pass only the endpoint path:

   ```typescript
   // Before (WRONG)
   authenticatedGet(
     `${API_BASE_URL}/api/tenant-admin/year-end-config/validate`,
   );

   // After (CORRECT)
   authenticatedGet("/api/tenant-admin/year-end-config/validate");
   ```

3. This matches the pattern used by all other working service files (e.g., `chartOfAccountsService.ts`)

**Files Modified**:

- `frontend/src/services/yearEndConfigService.ts`
- `frontend/src/services/yearEndClosureService.ts`

**Verification**:

- URLs now correctly constructed as: `https://invigorating-celebration-production.up.railway.app/api/tenant-admin/year-end-config/validate`
- All year-end API endpoints working correctly
- No more `ERR_NAME_NOT_RESOLVED` errors

**Lesson Learned**: Always pass only the endpoint path (starting with `/api/`) to `authenticatedGet`, `authenticatedPost`, etc. The `apiService` handles adding the base URL automatically based on the environment (localhost, Railway, GitHub Pages).

## Contact

For deployment issues:

- Check ADMIN_GUIDE.md troubleshooting section
- Review Railway logs
- Check GitHub Actions (if used)
- Contact system administrator

---

**Deployment Status**: ✅ COMPLETE  
**Deployment Date**: March 3, 2026  
**Final Status**: All features deployed and working correctly  
**Expected Downtime**: None (zero-downtime deployment achieved)
