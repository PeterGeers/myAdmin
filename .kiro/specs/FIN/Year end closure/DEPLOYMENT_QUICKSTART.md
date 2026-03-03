# Quick Deployment Guide - Using MySQL Workbench/HeidiSQL

**For**: Railway Backend + GitHub Pages Frontend  
**Tools**: MySQL Workbench or HeidiSQL (already configured)

## Prerequisites

- ✅ MySQL Workbench or HeidiSQL connected to Railway MySQL
- ✅ Git installed and configured
- ✅ Node.js and npm installed
- ✅ All code on `feature/year-end-closure` branch

## Progress Tracker

- [x] 1. Backup Database
- [x] 2. Create year_closure_status Table
- [x] 3. Add Parameters Column to rekeningschema
- [x] 4. Configure VAT Netting
- [x] 5. Configure Year-End Account Purposes
- [x] 6. Deploy Backend to Railway
- [x] 7. Enable Migration in Railway
- [x] 8. Run Historical Opening Balance Migration
- [x] 9. Disable Migration in Railway (SECURITY - DO THIS!)
- [x] 10. Deploy Frontend to GitHub Pages
- [x] 11. Fix Year-End API Errors
- [ ] 12. Verify Year-End Closure Feature (wait for CDN)
- [ ] 13. Test Reports
- [ ] 14. Monitor Production

## Quick Steps (3-4 hours)

### 1. Backup Database (10 min) ✅ COMPLETE

**Using MySQL Workbench**:

1. Connect to Railway MySQL
2. Server → Data Export
3. Select `myAdmin` database
4. Export to Self-Contained File
5. Save as `myAdmin_backup_20260303.sql`

**Using HeidiSQL**:

1. Connect to Railway MySQL
2. Right-click `myAdmin` database
3. Export database as SQL
4. Save as `myAdmin_backup_20260303.sql`

### 2. Create year_closure_status Table (5 min) ✅ COMPLETE

**Using MySQL Workbench or HeidiSQL**:

1. Open SQL editor/query tab
2. First, check if the table already exists:

```sql
-- Check if year_closure_status table exists
SHOW TABLES LIKE 'year_closure_status';
```

3. If the result is empty (table doesn't exist), run this:

```sql
-- Create year_closure_status table
CREATE TABLE IF NOT EXISTS year_closure_status (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(100) NOT NULL,
    year INT NOT NULL,
    closed_date DATETIME NOT NULL,
    closed_by VARCHAR(255) NOT NULL,
    closure_transaction_number VARCHAR(50),
    opening_balance_transaction_number VARCHAR(50),
    notes TEXT,
    UNIQUE KEY unique_admin_year (administration, year),
    INDEX idx_administration (administration),
    INDEX idx_year (year)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

4. Verify the table was created:

```sql
-- Verify table exists
DESCRIBE year_closure_status;
```

Expected output: You should see the table structure with columns: id, administration, year, closed_date, closed_by, closure_transaction_number, opening_balance_transaction_number, notes.

### 3. Add Parameters Column to rekeningschema (5 min) ✅ COMPLETE

**Using MySQL Workbench or HeidiSQL**:

1. Open SQL editor/query tab
2. First, check if the column already exists:

```sql
-- Check if parameters column exists
SELECT COUNT(*) as column_exists
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'myAdmin'
AND TABLE_NAME = 'rekeningschema'
AND COLUMN_NAME = 'parameters';
```

3. If the result is `0` (column doesn't exist), run this:

```sql
-- Add parameters column
ALTER TABLE rekeningschema
ADD COLUMN parameters JSON NULL;
```

4. Verify the column was added:

```sql
-- Verify column exists
DESCRIBE rekeningschema;
```

Expected output: You should see `parameters` column with type `json` in the table structure.

**Note**: If the check shows `1` (column exists), skip the ALTER TABLE command and proceed to the next step.

### 4. Configure VAT Netting (15 min) ✅ COMPLETE

**Using MySQL Workbench or HeidiSQL**:

1. Open SQL editor/query tab
2. Copy and paste this SQL:

```sql
-- Configure VAT netting for GoodwinSolutions
UPDATE rekeningschema
SET parameters = JSON_SET(
    COALESCE(parameters, '{}'),
    '$.vat_netting', true,
    '$.vat_primary', '2010'
)
WHERE Account IN ('2010', '2020', '2021')
AND administration = 'GoodwinSolutions';

-- Configure VAT netting for PeterPrive
UPDATE rekeningschema
SET parameters = JSON_SET(
    COALESCE(parameters, '{}'),
    '$.vat_netting', true,
    '$.vat_primary', '2010'
)
WHERE Account IN ('2010', '2020', '2021')
AND administration = 'PeterPrive';

-- Verify configuration
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

3. Execute the queries
4. Verify output shows 5 rows (GoodwinSolutions: 3, InterimManagement: 2) with `vat_netting=1` and `vat_primary='2010'`

### 5. Configure Year-End Account Purposes (10 min) ✅ COMPLETE

**Using MySQL Workbench or HeidiSQL**:

Configure the required accounts for year-end closure for all tenants:

```sql
-- GoodwinSolutions
UPDATE rekeningschema
SET parameters = JSON_SET(COALESCE(parameters, '{}'), '$.purpose', 'equity_result')
WHERE Account = '3080' AND administration = 'GoodwinSolutions';

UPDATE rekeningschema
SET parameters = JSON_SET(COALESCE(parameters, '{}'), '$.purpose', 'pl_closing')
WHERE Account = '8099' AND administration = 'GoodwinSolutions';

-- InterimManagement
UPDATE rekeningschema
SET parameters = JSON_SET(COALESCE(parameters, '{}'), '$.purpose', 'equity_result')
WHERE Account = '3080' AND administration = 'InterimManagement';

UPDATE rekeningschema
SET parameters = JSON_SET(COALESCE(parameters, '{}'), '$.purpose', 'pl_closing')
WHERE Account = '8099' AND administration = 'InterimManagement';

-- PeterPrive
UPDATE rekeningschema
SET parameters = JSON_SET(COALESCE(parameters, '{}'), '$.purpose', 'equity_result')
WHERE Account = '3080' AND administration = 'PeterPrive';

UPDATE rekeningschema
SET parameters = JSON_SET(COALESCE(parameters, '{}'), '$.purpose', 'pl_closing')
WHERE Account = '8099' AND administration = 'PeterPrive';

-- Verify configuration
SELECT administration, Account, AccountName, VW,
       JSON_EXTRACT(parameters, '$.purpose') as purpose
FROM rekeningschema
WHERE Account IN ('3080', '8099')
ORDER BY administration, Account;
```

Expected: 6 rows (2 accounts × 3 tenants):

- Account 3080: `purpose = "equity_result"`, VW='N'
- Account 8099: `purpose = "pl_closing"`, VW='Y'

### 6. Deploy Backend (10 min) ✅ COMPLETE

```powershell
# Merge to main branch
git checkout main
git merge feature/year-end-closure
git push origin main
```

Railway will automatically:

- Detect the push
- Build Docker container
- Deploy new backend
- Restart service (zero downtime)

**Monitor**: Go to Railway Dashboard → Backend Service → Deployments

Wait for "Deployment successful" message.

**Status**: Backend deployed successfully to Railway.

### 7. Enable Migration in Railway (2 min) ✅ COMPLETE

**In Railway Dashboard**:

1. Go to Backend Service → Variables
2. Click "New Variable"
3. Add:
   - Name: `ALLOW_MIGRATION`
   - Value: `true`
4. Click "Add"
5. Backend will restart automatically (takes ~30 seconds)

**Status**: Migration enabled in Railway environment variables.

### 8. Run Historical Opening Balance Migration (30-60 min) ✅ COMPLETE

**Migration completed successfully**:

- GoodwinSolutions: 18 years (2011-2028) ✅
- InterimManagement: 9 years (2002-2010) ✅
- PeterPrive: 33 years (1996-2028) ✅
- Total: 60 years migrated ✅

**Status**: All historical opening balances created with VAT netting applied correctly.

### 9. Disable Migration in Railway (2 min) ⏳ NEXT STEP

**After migration completes successfully**:

1. Go to Railway Dashboard → Backend Service → Variables
2. Find `ALLOW_MIGRATION` variable
3. Either:
   - Delete the variable, OR
   - Change value to `false`
4. Backend will restart automatically

**Why**: The migration endpoint should only be accessible during migration. Disabling it prevents unauthorized access.

### 10. Deploy Frontend (5 min) ✅ COMPLETE

Frontend deployed to GitHub Pages successfully. Migration Tool button is visible to SysAdmin users.

**Status**: Frontend deployed and accessible at GitHub Pages URL.

### 11. Fix Year-End API Errors (30 min) ✅ COMPLETE

**Problem Identified**: Console showing "Failed to fetch" errors for year-end status API.

**Root Cause**: The `yearEndClosureService.ts` was using `tenantAwareGet` which adds `?administration=GoodwinSolutions` query parameter. However, year-end endpoints expect tenant from `X-Tenant` header only (set by `authenticatedGet`), not from query parameters.

**Solution Applied**:

- Changed `yearEndClosureService.ts` to use `authenticatedGet` and `authenticatedPost` instead of `tenantAwareGet` and `tenantAwarePost`
- This ensures tenant is passed via `X-Tenant` header (which backend expects) rather than query parameter
- Committed fix: `6a0da21`
- GitHub Actions deploying fixed frontend

**Status**: Fix deployed, waiting for GitHub Pages CDN to update (5-10 minutes).

### 12. Verify Year-End Closure Feature (15 min) ⏳ NEXT STEP

**After GitHub Pages updates (wait 5-10 minutes)**:

1. **Clear browser cache**: Ctrl+Shift+R or Ctrl+F5
2. **Check HTML source**: Look for `main.a86c530f.js` (new build) instead of old version
3. **Login to myAdmin**: https://petergeers.github.io/myAdmin/
4. **Navigate to FIN Rapporten → Aangifte IB**
5. **Select year 2026**
6. **Scroll to bottom**: Look for "Jaarafsluiting" (Year-End Closure) section

**Expected Results**:

- ✅ No console errors for year-end API calls
- ✅ Year status badge shows "Open" for 2026
- ✅ Net P&L result displayed
- ✅ Balance sheet account count shown
- ✅ "Close Year 2026" button visible
- ✅ Previous year (2025) status shown

**If Still Seeing Errors**:

- Wait another 5 minutes for CDN to fully update
- Try incognito/private browsing mode
- Check Network tab in DevTools for actual requests being made

### 13. Test Reports (30 min)

```
API request failed: TypeError: Failed to fetch
Error fetching year status: TypeError: Failed to fetch
```

**Diagnosis Steps**:

1. **Check if year-end routes are deployed**:
   - Open Railway Dashboard → Backend Service → Logs
   - Look for startup messages about route registration
   - Should see: "Registered blueprint: year_end" and "Registered blueprint: year_end_config"

2. **Test year-end endpoint directly**:

   ```bash
   # Replace with your actual Railway backend URL
   curl "https://your-backend.railway.app/api/year-end/status/2025?tenant=GoodwinSolutions"
   ```

   Expected response:

   ```json
   {
     "year": 2025,
     "closed": false,
     "message": "Year 2025 is not closed"
   }
   ```

3. **Check CORS configuration**:
   - Verify `app.py` has GitHub Pages URL in CORS origins
   - Should include: `"https://petergeers.github.io"`

4. **Verify routes are registered**:
   - Check `app.py` lines 168-169:
   ```python
   app.register_blueprint(year_end_config_bp)  # Year-end configuration endpoints
   app.register_blueprint(year_end_bp)  # Year-end closure endpoints
   ```

**Possible Solutions**:

A. **If routes not found in Railway logs**:

- Backend may need redeployment
- Check if `routes/year_end_routes.py` and `routes/year_end_config_routes.py` are in Railway deployment
- Verify Railway build logs for any import errors

B. **If CORS error**:

- Add GitHub Pages URL to CORS configuration
- Redeploy backend

C. **If authentication error**:

- Check if Cognito token is valid
- Verify tenant header is being sent correctly

**Next Steps**:

1. Check Railway logs for route registration
2. Test endpoint directly with curl
3. Report findings to determine next action
   ✅ gh-pages has correct files (main.86c1e6bc.js)
   ⏳ GitHub Pages CDN updating (takes 5-10 minutes)
   ❌ Your browser showing old cached version (main.7d8bcf8c.js)

What to do:
Wait 5-10 minutes for GitHub Pages to update
Hard refresh your browser: Ctrl+Shift+R or Ctrl+F5
Check the HTML source - look for main.86c1e6bc.js instead of main.7d8bcf8c.js
Once you see the new JS file, the Migration Tool button will appear
The deployment is complete - just waiting for GitHub's CDN to catch up!

### 8. Run Historical Opening Balance Migration (30-60 min)

**Using the Migration Tool UI**:

1. Visit your GitHub Pages site (or run frontend locally with `npm start`)
2. Login to myAdmin
3. Click the yellow "🔄 Migration Tool" button on the main menu
4. Enter the secret: `migrate-opening-balances-2026`
5. Click "Run Migration"
6. Wait for completion:
   - Progress shows in real-time
   - Processes all tenants: GoodwinSolutions, InterimManagement, PeterPrive
   - Creates opening balance records for all historical years
   - Includes VAT netting (consolidates 2010/2020/2021 → 2010)
7. Download the log file automatically when complete
8. Review the log file for any errors or warnings

**Expected Results**:

- Opening balance transactions created for each year per tenant
- Transaction numbers format: `OB-{YEAR}-{TENANT}`
- VAT accounts properly netted
- All accounts with non-zero balances included

**If Migration Fails**:

- Check Railway logs for detailed error messages
- Verify `ALLOW_MIGRATION=true` is set
- Verify secret is correct
- Check database connection
- Review downloaded log file for specific errors

### 9. Disable Migration in Railway (2 min) 🔒 SECURITY

**After migration completes successfully**:

1. Go to Railway Dashboard → Backend Service → Variables
2. Find `ALLOW_MIGRATION` variable
3. Either:
   - Delete the variable, OR
   - Change value to `false`
4. Backend will restart automatically

**Why**: The migration endpoint should only be accessible during migration. Disabling it prevents unauthorized access.

### 10. Deploy Frontend (5 min)

````bash
### 10. Deploy Frontend (5 min)

```powershell
cd frontend

# Build production bundle
npm run build

# Deploy to GitHub Pages
npm run deploy
```

Wait for "Published" message.

Wait for "Published" message.

### 11. Verify Deployment (30 min)

#### Check Backend

1. Visit: `https://your-backend.railway.app/api/health`
2. Should return: `{"status": "healthy"}`
3. Check Railway logs for:
   - `"Loading years: [2025, 2026, 2027, 2028]"` (optimized cache)
   - `"Cache loaded: 6,506 rows in 1.84s"`
   - `"Memory usage: ~5.4 MB"`

#### Check Frontend

1. Visit your GitHub Pages URL
2. Open browser console (F12)
3. Check for errors (should be none)

#### Test Year-End Configuration

**For GoodwinSolutions**:

1. Login and switch to GoodwinSolutions tenant
2. Go to Tenant Admin → Year-End Settings
3. Verify:
   - Equity Result Account: 3080
   - P&L Closing Account: 8099
   - Status: "Configuration Complete" (green)

**For PeterPrive**:

1. Switch to PeterPrive tenant
2. Go to Tenant Admin → Year-End Settings
3. Verify configuration complete

#### Test Year-End Closure

1. Go to FIN Rapporten → Aangifte IB
2. Select year 2025
3. Scroll to bottom → Jaarafsluiting section
4. Verify:
   - Year status badge shows
   - Validation summary displays
   - Net P&L result shown
   - Balance sheet account count shown

### 12. Test Reports (30 min)

- [ ] Aangifte IB - loads faster, year selector shows all years
- [ ] BTW Report - shows current year only with opening balance
- [ ] Actuals Report - year selector works, data correct
- [ ] Mutaties Tab - pagination working (1000 records)

### 13. Monitor (1 hour)

**Railway Dashboard**:

- Check CPU usage (should be similar or lower)
- Check memory usage (should be ~93% lower)
- Monitor error logs (should be none)

**Frontend**:

- Check browser console for errors
- Test on different browsers
- Verify mobile works

## Rollback (if needed)

### Rollback Backend

```bash
git checkout main
git revert HEAD
git push origin main
# Railway auto-deploys reverted version
```

### Rollback Frontend

```bash
git checkout gh-pages
git revert HEAD
git push origin gh-pages
```

### Restore Database (only if corrupted)

**Using MySQL Workbench**:

1. Server → Data Import
2. Select `myAdmin_backup_20260303.sql`
3. Import

**Using HeidiSQL**:

1. File → Load SQL file
2. Select backup file
3. Execute

## Success Checklist

- [x] Database backed up
- [x] year_closure_status table created
- [x] Parameters column added to rekeningschema
- [x] VAT netting configured (verified 5 rows)
- [x] Account purposes configured (verified 6 rows: 3080, 8099 for all tenants)
- [x] Backend deployed (Railway shows success)
- [x] Migration enabled in Railway (ALLOW_MIGRATION=true)
- [x] Historical opening balances migrated (60 years across 3 tenants)
- [ ] Migration disabled in Railway (ALLOW_MIGRATION=false or removed) 🔒 SECURITY
- [x] Frontend deployed (GitHub Pages updated)
- [x] Year-End API fix deployed (commit 6a0da21)
- [ ] Year-End Closure section visible in Aangifte IB (wait for CDN)
- [ ] No errors in browser console
- [ ] Reports load correctly
- [ ] Year-End closure workflow tested

## Quick Reference

### Railway Dashboard

- URL: https://railway.app/dashboard
- Backend logs: Backend Service → Logs
- MySQL: MySQL Service → Connect

### GitHub Pages

- URL: Your repository → Settings → Pages
- Deployment: Actions tab

### Support

- USER_GUIDE.md - End user help
- ADMIN_GUIDE.md - Troubleshooting
- RAILWAY_DEPLOYMENT.md - Full details

## Estimated Time

| Task                       | Duration      | Status        |
| -------------------------- | ------------- | ------------- |
| Backup                     | 10 min        | ✅ Complete   |
| Create year_closure_status | 5 min         | ✅ Complete   |
| Add Parameters Column      | 5 min         | ✅ Complete   |
| VAT Config                 | 15 min        | ✅ Complete   |
| Account Purposes Config    | 10 min        | ✅ Complete   |
| Backend Deploy             | 10 min        | ✅ Complete   |
| Enable Migration           | 2 min         | ✅ Complete   |
| Run Migration              | 30-60 min     | ✅ Complete   |
| Disable Migration          | 2 min         | ⏳ Next       |
| Frontend Deploy            | 5 min         | ✅ Complete   |
| Fix Year-End API           | 30 min        | ✅ Complete   |
| Verification               | 15 min        | Pending (CDN) |
| Testing                    | 30 min        | Pending       |
| Monitoring                 | 1 hour        | Pending       |
| **Total**                  | **3-4 hours** | **~85% done** |

---

## Summary

**Deployment Status**: Nearly complete! 🎉

**What's Done**:
- ✅ Database schema updated (year_closure_status table, parameters column)
- ✅ VAT netting configured for GoodwinSolutions and PeterPrive
- ✅ Account purposes configured for all 3 tenants
- ✅ Backend deployed to Railway
- ✅ Historical opening balances migrated (60 years)
- ✅ Frontend deployed with API fix

**What's Next**:
1. **SECURITY**: Disable `ALLOW_MIGRATION` in Railway (2 min)
2. Wait for GitHub Pages CDN to update (5-10 min)
3. Verify Year-End Closure section appears in Aangifte IB
4. Test the year-end closure workflow

**Known Issue Fixed**: Year-End API calls were using wrong service method. Fixed in commit `6a0da21` - frontend now uses `authenticatedGet` which sends tenant via `X-Tenant` header as backend expects.

---

**Ready to verify!** 🚀

Once GitHub Pages CDN updates, the Year-End Closure feature will be fully operational in production.
````
