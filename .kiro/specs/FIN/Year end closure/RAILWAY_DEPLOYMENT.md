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
- [ ] Database backup created
- [ ] Stakeholder approval obtained

## Step 1: Backup Production Database (15 min)

### Option A: Using Railway CLI (Recommended)

```bash
# Install Railway CLI if not installed
npm i -g @railway/cli

# Login to Railway
railway login

# Link to your project (if not already linked)
railway link

# Create backup
railway run mysqldump -u root -p[PASSWORD] myAdmin > myAdmin_backup_$(date +%Y%m%d).sql
```

### Option B: Using MySQL Workbench/DBeaver

1. Get connection details from Railway Dashboard:
   - Go to MySQL service → Connect tab
   - Copy: Host, Port, User, Password, Database
2. Connect using MySQL Workbench or DBeaver
3. Export database: Server → Data Export
4. Save as `myAdmin_backup_YYYYMMDD.sql`

### Option C: Using Railway Dashboard

1. Go to Railway project → MySQL service
2. Click "Data" tab
3. Use "Export" feature (if available)

## Step 2: Verify Database Schema (5 min)

**The schema changes are already applied!** ✅

Verify (optional):

```bash
railway run mysql -u root -p[PASSWORD] myAdmin -e "SHOW TABLES LIKE 'year_closure_status';"
railway run mysql -u root -p[PASSWORD] myAdmin -e "DESCRIBE rekeningschema;" | grep parameters
```

Expected output:

- `year_closure_status` table exists
- `rekeningschema` has `parameters` JSON column

## Step 3: Configure VAT Netting (15 min per tenant)

### For GoodwinSolutions

```bash
railway run python backend/scripts/database/configure_vat_netting.py --administration GoodwinSolutions
```

### For PeterPrive

```bash
railway run python backend/scripts/database/configure_vat_netting.py --administration PeterPrive
```

### Verify Configuration

```bash
railway run mysql -u root -p[PASSWORD] myAdmin -e "
SELECT Account, AccountName,
       JSON_EXTRACT(parameters, '$.vat_netting') as vat_netting,
       JSON_EXTRACT(parameters, '$.vat_primary') as vat_primary
FROM rekeningschema
WHERE Account IN ('2010', '2020', '2021')
AND administration = 'GoodwinSolutions';
"
```

Expected: All three accounts have `vat_netting=true` and `vat_primary='2010'`

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
- [ ] All reports working correctly
- [ ] Year-end closure feature functional
- [ ] Performance improvements verified
- [ ] No critical bugs
- [ ] Cache optimization working
- [ ] User feedback positive

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

## Contact

For deployment issues:

- Check ADMIN_GUIDE.md troubleshooting section
- Review Railway logs
- Check GitHub Actions (if used)
- Contact system administrator

---

**Deployment Status**: Ready ✅  
**Recommended Time**: Evening or weekend (low traffic)  
**Expected Downtime**: None (zero-downtime deployment)
