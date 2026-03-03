# Historical Year Closure Data Migration

**Date**: March 2, 2026  
**Status**: ✅ Complete  
**Script**: `backend/scripts/database/populate_year_closure_history.py`

## Overview

Successfully migrated 54 historical year closures into the `year_closure_status` table by analyzing existing opening balance records in the `mutaties` table.

## Migration Results

### Summary by Tenant

| Tenant            | Total Years | With Closure Txn | NULL Closure Txn |
| ----------------- | ----------- | ---------------- | ---------------- |
| GoodwinSolutions  | 15          | 14               | 1                |
| InterimManagement | 9           | 9                | 0                |
| PeterPrive        | 30          | 20               | 10               |
| **TOTAL**         | **54**      | **43**           | **11**           |

### Year Ranges

- **GoodwinSolutions**: 2010-2024 (15 years)
- **InterimManagement**: 2001-2009 (9 years)
- **PeterPrive**: 1995-2024 (30 years)

## NULL Closure Transaction Numbers

### What Are They?

11 records (20% of total) have `closure_transaction_number = NULL`:

**GoodwinSolutions**:

- 2010

**PeterPrive**:

- 1995, 1996, 1997, 1998, 1999, 2000, 2001
- 2022, 2023, 2024

### Why NULL?

The migration script looked for transactions with `TransactionNumber = "Afsluiting YYYY"` to link as closure transactions. For these 11 years, no such transactions existed in the historical data.

**Possible reasons**:

1. Years were closed manually without creating formal closure transactions
2. Closure transactions were created with different naming conventions
3. Data was migrated from another system without closure transactions
4. Opening balances were created directly without going through a closure process

### Is This a Problem?

**No, this is perfectly acceptable** for the following reasons:

1. **Opening Balances Exist**: All 54 records have valid `opening_balance_transaction_number` values
2. **System Functionality**: The year-end closure system only requires opening balances to function
3. **Historical Data**: These are historical records from before the formal year-end closure feature existed
4. **Documentation**: The `notes` field documents which years lack closure transactions
5. **Future Closures**: All future closures (done through the UI) will have both fields populated

### Example Record with NULL

```json
{
  "id": 25,
  "administration": "PeterPrive",
  "year": 1995,
  "closed_date": "1995-12-31 23:59:59",
  "closed_by": "system_migration",
  "closure_transaction_number": null,
  "opening_balance_transaction_number": "OpeningBalance 1996",
  "notes": "Historical closure - migrated from opening balance records. Opening balance: OpeningBalance 1996. No 'Afsluiting 1995' transaction found."
}
```

## Migration Logic

### How It Works

1. **Find Opening Balances**: Query `mutaties` for records with `TransactionNumber LIKE 'OpeningBalance %'`
2. **Extract Year**: Parse the year from the transaction number (e.g., "OpeningBalance 2025" → 2025)
3. **Calculate Closed Year**: Opening balance year - 1 (e.g., 2025 → 2024 was closed)
4. **Check for Closure Transaction**: Look for `TransactionNumber = 'Afsluiting YYYY'`
5. **Insert Record**: Create year_closure_status record with:
   - `closure_transaction_number`: "Afsluiting YYYY" if found, NULL otherwise
   - `opening_balance_transaction_number`: "OpeningBalance YYYY+1"
   - `closed_date`: December 31 of closed year
   - `closed_by`: "system_migration"
   - `notes`: Documentation of what was found

### SQL Query Example

```sql
-- Find opening balance years for a tenant
SELECT DISTINCT
    CAST(SUBSTRING(TransactionNumber, 16) AS UNSIGNED) as opening_year
FROM mutaties
WHERE administration = 'GoodwinSolutions'
AND TransactionNumber LIKE 'OpeningBalance %'
AND TransactionNumber REGEXP 'OpeningBalance [0-9]+'
ORDER BY opening_year;

-- Check if closure transaction exists
SELECT COUNT(*) as count
FROM mutaties
WHERE administration = 'GoodwinSolutions'
AND TransactionNumber = 'Afsluiting 2024';
```

## Impact on System

### Available Years for Closure

Before migration:

- GoodwinSolutions: 2010-2028 (19 years available)
- PeterPrive: 1995-2028 (34 years available)

After migration:

- GoodwinSolutions: 2025-2028 (4 years available)
- PeterPrive: 2025-2028 (4 years available)

### Frontend Display

The Year-End Closure tab in FIN Reports now shows:

- **Closed Years Table**: 54 historical records
- **Available Years**: 2025-2028 (current and future years)
- **Status**: System correctly prevents re-closing historical years

### Validation Logic

The `YearEndClosureService.validate_year_closure()` method:

- ✅ Correctly identifies years as already closed
- ✅ Prevents duplicate closures
- ✅ Enforces sequential closure (previous year must be closed)
- ✅ Works with NULL closure_transaction_number values

## Verification

### Check Script

Created `backend/scripts/database/check_null_closures.py` to verify:

- Count records by tenant
- List all NULL closure_transaction_number records
- Verify opening_balance_transaction_number is always populated

### Run Verification

```bash
cd backend
.\.venv\Scripts\python.exe scripts/database/check_null_closures.py
```

### Expected Output

```
Year Closure Status Summary by Tenant:
================================================================================
GoodwinSolutions     | Total: 15 | With Closure: 14 | NULL Closure:  1
InterimManagement    | Total:  9 | With Closure:  9 | NULL Closure:  0
PeterPrive           | Total: 30 | With Closure: 20 | NULL Closure: 10

Total records with NULL closure_transaction_number: 11
```

## Next Steps

### Task 2: Manual Year 2025 Closure

User will manually close year 2025 using the frontend UI for:

- GoodwinSolutions
- PeterPrive

This will:

1. Test the full year closure workflow with real data
2. Create both closure and opening balance transactions
3. Verify the system works end-to-end
4. Provide examples of complete closure records (with both transaction numbers)

### Future Considerations

1. **Optional Backfill**: If needed, could create "Afsluiting YYYY" transactions for the 11 years with NULL
   - Not required for system functionality
   - Would only be for data completeness/consistency
   - Low priority

2. **Reporting**: Reports should handle NULL closure_transaction_number gracefully
   - Display "N/A" or "Historical" for NULL values
   - Don't break if closure transaction is missing

3. **Audit Trail**: The notes field provides full audit trail for historical migrations

## Conclusion

The historical data migration was successful. The 11 records with NULL `closure_transaction_number` are:

- **Expected**: Historical data didn't have formal closure transactions
- **Acceptable**: Opening balances exist, which is what matters
- **Documented**: Notes field explains the situation
- **No Impact**: System functions correctly with NULL values

All 54 years are now properly marked as closed, preventing duplicate closures and enabling the year-end closure feature to work correctly going forward.

---

**Migration Complete**: ✅  
**System Status**: Ready for production use  
**Next Action**: User to test manual closure of year 2025
