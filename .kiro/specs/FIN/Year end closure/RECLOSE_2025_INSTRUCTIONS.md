# Re-Close Year 2025 - Instructions

**Date**: March 2, 2026  
**Status**: Ready to execute  
**Reason**: Fix incorrect opening balance calculation

## Summary of Fixes

1. ✅ Use `vw_mutaties` view instead of raw `mutaties` table
2. ✅ Exclude opening balance and closure transactions from balance calculation
3. ✅ Remove ReferenceNumber from INSERT statements (should be NULL)
4. ✅ Improve transaction descriptions to include account names

## Step 1: Run Cleanup Script

Delete the incorrect 2025 closure data:

```bash
cd backend
.\.venv\Scripts\python.exe scripts/database/cleanup_2025_closure.py
```

**What it does**:

- Deletes all OpeningBalance 2026 transactions
- Deletes YearClose 2025 transaction
- Deletes year_closure_status record for 2025

**Expected output**:

```
CLEANUP 2025 YEAR CLOSURE
1. Deleting OpeningBalance 2026 transactions...
   ✅ Deleted OpeningBalance 2026 transactions
2. Deleting YearClose 2025 transaction...
   ✅ Deleted YearClose 2025 transaction
3. Deleting year_closure_status record for 2025...
   ✅ Deleted year_closure_status record

VERIFICATION
Mutaties records remaining: 0 (should be 0)
Year closure status records: 0 (should be 0)

CLEANUP COMPLETE
```

## Step 2: Restart Backend

Restart the Docker container to load the fixed code:

```bash
docker-compose restart backend
```

**Wait for**: Container status shows "healthy"

```bash
docker-compose ps backend
```

Should show: `Up X seconds (healthy)`

## Step 3: Re-Close Year 2025

1. Open browser and navigate to FIN Reports
2. Click on **📅 Year-End Closure** tab
3. Click **"Boekjaar Afsluiten"** button
4. Select **2025** from dropdown
5. Click **"Volgende"** (Next)

**Verify validation results**:

- ✅ No errors
- ✅ Net P&L result looks reasonable
- ✅ Balance sheet accounts count looks correct

6. Add optional notes (e.g., "Re-closed with fixed calculation")
7. Click **"Sluit Jaar 2025"** (Close Year 2025)

**Expected success message**:
"Year 2025 closed successfully"

## Step 4: Verify Results

### Check Closed Years Table

Should show:

- Year: 2025
- Closed Date: Today's date
- Closed By: your email
- Notes: Your notes
- Status: Closed

### Check OpeningBalance 2026 in Database

Run this query:

```sql
SELECT
    Reknum,
    TransactionDescription,
    TransactionAmount,
    Debet,
    Credit,
    ReferenceNumber
FROM mutaties
WHERE TransactionNumber LIKE 'OpeningBalance 2026%'
AND administration = 'GoodwinSolutions'
ORDER BY Reknum
LIMIT 10;
```

**Verify**:

- ✅ ReferenceNumber is NULL (not "OpeningBalance 2026")
- ✅ Descriptions include account names (e.g., "Opening balance 2026 for Rabobank Rekening Courant")
- ✅ Amounts are reasonable (similar magnitude to OpeningBalance 2025)
- ✅ No transactions with Debet = Credit
- ✅ All use interim account 2001 as offset

### Compare with OpeningBalance 2025

Run this query to compare:

```sql
SELECT
    '2025' as year,
    Reknum,
    TransactionAmount,
    ReferenceNumber
FROM mutaties
WHERE TransactionNumber LIKE 'OpeningBalance 2025%'
AND administration = 'GoodwinSolutions'
AND Reknum IN ('1002', '1011', '1012', '2010', '3080')

UNION ALL

SELECT
    '2026' as year,
    Reknum,
    TransactionAmount,
    ReferenceNumber
FROM mutaties
WHERE TransactionNumber LIKE 'OpeningBalance 2026%'
AND administration = 'GoodwinSolutions'
AND Reknum IN ('1002', '1011', '1012', '2010', '3080')

ORDER BY Reknum, year;
```

**Expected pattern**:

```
Year | Reknum | Amount    | ReferenceNumber
-----|--------|-----------|----------------
2025 | 1002   | 12,118    | NULL
2026 | 1002   | ~12,xxx   | NULL  ← Should be similar

2025 | 1011   | 47,025    | NULL
2026 | 1011   | ~47,xxx   | NULL  ← Should be similar (NOT 1,360,301!)

2025 | 2010   | 157,393   | NULL
2026 | 2010   | ~xxx,xxx  | NULL  ← Should be similar
```

### Check Balance Totals

Run this query:

```sql
SELECT
    TransactionNumber,
    SUM(CASE WHEN Debet = '2001' THEN TransactionAmount ELSE 0 END) as total_debet,
    SUM(CASE WHEN Credit = '2001' THEN TransactionAmount ELSE 0 END) as total_credit,
    COUNT(*) as record_count
FROM mutaties
WHERE TransactionNumber IN ('OpeningBalance 2025', 'OpeningBalance 2026')
AND administration = 'GoodwinSolutions'
GROUP BY TransactionNumber;
```

**Verify**:

- ✅ total_debet = total_credit (balanced)
- ✅ record_count is reasonable (number of balance sheet accounts)

## Step 5: Test with PeterPrive (Optional)

If GoodwinSolutions looks good, repeat for PeterPrive:

1. Run cleanup for PeterPrive (modify script or run manually)
2. Close year 2025 for PeterPrive
3. Verify results

## Troubleshooting

### Issue: "Year already closed"

**Solution**: Cleanup script didn't run successfully. Manually delete:

```sql
DELETE FROM year_closure_status WHERE administration = 'GoodwinSolutions' AND year = 2025;
DELETE FROM mutaties WHERE administration = 'GoodwinSolutions' AND TransactionNumber LIKE 'OpeningBalance 2026%';
DELETE FROM mutaties WHERE administration = 'GoodwinSolutions' AND TransactionNumber LIKE 'YearClose 2025%';
```

### Issue: "Insufficient permissions"

**Solution**: Backend not restarted. Run:

```bash
docker-compose restart backend
```

### Issue: Amounts still look wrong

**Solution**: Check that backend restarted and loaded new code:

```bash
docker-compose logs backend | grep "year_end_service"
```

Should show the service loading.

## Success Criteria

- ✅ OpeningBalance 2026 created successfully
- ✅ Amounts match expected pattern (similar to 2025)
- ✅ ReferenceNumber is NULL
- ✅ Descriptions include account names
- ✅ No invalid transactions (Debet = Credit)
- ✅ Total Debet = Total Credit
- ✅ Year 2025 marked as closed in year_closure_status

## Files Modified

- `backend/src/services/year_end_service.py`
  - `_get_ending_balances()` - Use vw_mutaties
  - `_calculate_net_pl_result()` - Use vw_mutaties
  - `_count_balance_sheet_accounts()` - Use vw_mutaties
  - `_create_opening_balances()` - Remove ReferenceNumber, improve descriptions
  - `_create_closure_transaction()` - Remove ReferenceNumber

## Related Documentation

- `.kiro/specs/FIN/Year end closure/BUG_FIX_OPENING_BALANCE.md` - Detailed bug analysis
- `.kiro/specs/FIN/Year end closure/HISTORICAL_DATA_MIGRATION.md` - Historical context
- `backend/scripts/database/migrate_opening_balances.py` - Reference implementation
