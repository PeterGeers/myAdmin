# Quick Deployment Guide - Using MySQL Workbench/HeidiSQL

**For**: Railway Backend + GitHub Pages Frontend  
**Tools**: MySQL Workbench or HeidiSQL (already configured)

## Prerequisites

- ✅ MySQL Workbench or HeidiSQL connected to Railway MySQL
- ✅ Git installed and configured
- ✅ Node.js and npm installed
- ✅ All code on `feature/year-end-closure` branch

## Quick Steps (2-3 hours)

### 1. Backup Database (10 min)

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

### 2. Add Parameters Column to rekeningschema (5 min)

**Using MySQL Workbench or HeidiSQL**:

1. Open SQL editor/query tab
2. Run this SQL to add the `parameters` column:

```sql
-- Add parameters column if it doesn't exist
ALTER TABLE rekeningschema
ADD COLUMN IF NOT EXISTS parameters JSON NULL;

-- Verify column was added
DESCRIBE rekeningschema;
```

Expected output: You should see `parameters` column with type `json` in the table structure.

**Note**: If the column already exists, the `IF NOT EXISTS` clause will prevent an error.

### 3. Configure VAT Netting (15 min)

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
4. Verify output shows 6 rows with `vat_netting=1` and `vat_primary='2010'`

### 3. Deploy Backend (10 min)

```bash
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

### 4. Deploy Frontend (5 min)

```bash
cd frontend

# Build production bundle
npm run build

# Deploy to GitHub Pages
npm run deploy
```

Wait for "Published" message.

### 5. Verify Deployment (30 min)

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

### 6. Test Reports (30 min)

- [ ] Aangifte IB - loads faster, year selector shows all years
- [ ] BTW Report - shows current year only with opening balance
- [ ] Actuals Report - year selector works, data correct
- [ ] Mutaties Tab - pagination working (1000 records)

### 7. Monitor (1 hour)

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

- [ ] Database backed up
- [ ] Parameters column added to rekeningschema
- [ ] VAT netting configured (verified 6 rows)
- [ ] Backend deployed (Railway shows success)
- [ ] Frontend deployed (GitHub Pages updated)
- [ ] Year-End Settings show "Complete" for both tenants
- [ ] Aangifte IB shows Jaarafsluiting section
- [ ] Reports load faster
- [ ] No errors in logs
- [ ] No errors in browser console

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

| Task                  | Duration      |
| --------------------- | ------------- |
| Backup                | 10 min        |
| Add Parameters Column | 5 min         |
| VAT Config            | 15 min        |
| Backend Deploy        | 10 min        |
| Frontend Deploy       | 5 min         |
| Verification          | 30 min        |
| Testing               | 30 min        |
| Monitoring            | 1 hour        |
| **Total**             | **2-3 hours** |

---

**Ready to deploy!** 🚀

Follow these steps in order, and you'll have the Year-End Closure feature live in production with zero downtime.
