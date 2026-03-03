# Bug Fix: Opening Balance Calculation

**Date**: March 2, 2026  
**Issue**: OpeningBalance 2026 had incorrect amounts and invalid transactions  
**Status**: ✅ Fixed

## Problem

When closing year 2025, the OpeningBalance 2026 transactions were created with:

1. **Incorrect amounts** - Much larger than expected (e.g., €47,025 → €1,360,301)
2. **Invalid transaction** - One record with Debet=2001, Credit=2001 (same account)
3. **Wrong ReferenceNumber** - Set to "OpeningBalance 2026" instead of NULL

## Root Cause

The `year_end_service.py` was using the raw `mutaties` table instead of the `vw_mutaties` view:

### Issue 1: Complex Balance Calculation

```python
# WRONG - Using mutaties table with complex CASE logic
SELECT
    SUM(
        CASE
            WHEN m.Debet = r.Account THEN m.TransactionAmount
            WHEN m.Credit = r.Account THEN -m.TransactionAmount
            ELSE 0
        END
    ) as balance
FROM mutaties m
JOIN rekeningschema r ON (m.Debet = r.Account OR m.Credit = r.Account)
```

This caused:

- Double counting (account appears in both Debet and Credit joins)
- Incorrect sign calculation
- Including opening balance transactions in the sum

### Issue 2: ReferenceNumber Field

```python
# WRONG - Setting ReferenceNumber to transaction number
INSERT INTO mutaties (..., ReferenceNumber, ...)
VALUES (..., transaction_number, ...)
```

Historical OpeningBalance 2025 records have `ReferenceNumber = NULL`.

## Solution

### Use vw_mutaties View

The `vw_mutaties` view already has:

- `Amount` column with correct sign (positive for debit, negative for credit)
- `Reknum` column for account number
- `VW` column for account classification
- Proper handling of debit/credit logic

### Updated Methods

1. **\_get_ending_balances()**

```python
# CORRECT - Using vw_mutaties view
SELECT
    Reknum as account,
    AccountName as account_name,
    SUM(Amount) as balance
FROM vw_mutaties
WHERE administration = %s
AND VW = 'N'
AND TransactionDate <= %s
AND TransactionNumber NOT LIKE 'OpeningBalance%%'
AND TransactionNumber NOT LIKE 'Afsluiting%%'
AND TransactionNumber NOT LIKE 'YearClose%%'
GROUP BY Reknum, AccountName
HAVING ABS(SUM(Amount)) > 0.01
```

2. **\_calculate_net_pl_result()**

```python
# CORRECT - Using vw_mutaties view
SELECT
    COALESCE(SUM(Amount), 0) as net_result
FROM vw_mutaties
WHERE administration = %s
AND YEAR(TransactionDate) = %s
AND VW = 'Y'
```

3. **\_count_balance_sheet_accounts()**

```python
# CORRECT - Using vw_mutaties view
SELECT COUNT(DISTINCT Reknum) as count
FROM (
    SELECT
        Reknum,
        SUM(Amount) as balance
    FROM vw_mutaties
    WHERE administration = %s
    AND VW = 'N'
    AND TransactionDate <= %s
    AND TransactionNumber NOT LIKE 'OpeningBalance%%'
    GROUP BY Reknum
    HAVING ABS(SUM(Amount)) > 0.01
) as accounts_with_balance
```

4. **Removed ReferenceNumber from INSERT**

```python
# CORRECT - No ReferenceNumber field
INSERT INTO mutaties (
    TransactionNumber,
    TransactionDate,
    TransactionDescription,
    TransactionAmount,
    Debet,
    Credit,
    administration
) VALUES (%s, %s, %s, %s, %s, %s, %s)
```

## Files Changed

- `backend/src/services/year_end_service.py`
  - `_get_ending_balances()` - Use vw_mutaties, exclude bookkeeping transactions
  - `_calculate_net_pl_result()` - Use vw_mutaties
  - `_count_balance_sheet_accounts()` - Use vw_mutaties
  - `_create_opening_balances()` - Remove ReferenceNumber from INSERT
  - `_create_closure_transaction()` - Remove ReferenceNumber from INSERT

## Why This Works

The migration script (`migrate_opening_balances.py`) worked perfectly because it:

1. Used `vw_mutaties` view from the start
2. Excluded opening balance transactions: `TransactionNumber NOT LIKE 'OpeningBalance%'`
3. Used the `Amount` column which has correct sign
4. Didn't set ReferenceNumber field

## Cleanup Steps

1. **Run cleanup script**:

```bash
cd backend
.\.venv\Scripts\python.exe scripts/database/cleanup_2025_closure.py
```

This deletes:

- OpeningBalance 2026 transactions (incorrect)
- YearClose 2025 transaction
- year_closure_status record for 2025

2. **Restart backend**:

```bash
docker-compose restart backend
```

3. **Re-close year 2025**:

- Go to FIN Reports → Year-End Closure
- Click "Boekjaar Afsluiten"
- Select 2025
- Click "Volgende"
- Verify amounts look correct
- Click "Sluit Jaar 2025"

## Expected Results

After re-closing with the fix:

**OpeningBalance 2026 should match OpeningBalance 2025 pattern**:

- ReferenceNumber: NULL (not "OpeningBalance 2026")
- Amounts: Similar magnitude to 2025 opening balances
- No invalid transactions (same account on both sides)
- All transactions use interim account 2001 as offset

**Comparison**:

```
2025: €12,118  (1002 → 2001)  ✓ Correct
2026: €12,xxx  (1002 → 2001)  ✓ Should be similar

NOT:
2026: €1,360,301 (1011 → 2001)  ✗ Wrong (was including opening balance)
```

## Validation

After re-closing, verify:

1. OpeningBalance 2026 amounts are reasonable
2. No transactions with Debet = Credit
3. ReferenceNumber is NULL for all opening balance records
4. Total Debet = Total Credit for opening balances
5. Balances match the ending balances from 2025

## Lessons Learned

1. **Use vw_mutaties for balance calculations** - It handles debit/credit logic correctly
2. **Exclude bookkeeping transactions** - Opening balances and closures shouldn't be included in balance calculations
3. **Match historical patterns** - New records should look like existing historical records
4. **Test with real data** - The bug only appeared when testing with actual year closure

## Related Files

- `backend/src/services/year_end_service.py` - Fixed service
- `backend/scripts/database/migrate_opening_balances.py` - Reference implementation (correct)
- `backend/scripts/database/cleanup_2025_closure.py` - Cleanup script
- `.kiro/specs/FIN/Year end closure/HISTORICAL_DATA_MIGRATION.md` - Historical data context
