# June 2025 Revolut Transaction Re-Import Guide

## Problem Summary

- **First 10 transactions (May)**: Perfect, 0.00 discrepancy ✓
- **Gap starts at ID 60333 (June 12)**: 45.86 euro discrepancy
- **Consistent 17.35 euro gap**: Throughout June/July transactions
- **Root cause**: Transactions imported out of chronological order

## Investigation Findings

1. **Out-of-order imports detected**:
   - ID 60307: June 17 transaction
   - IDs 60308-60332: Non-Revolut transactions (25 transactions)
   - ID 60333: June 12 transaction (earlier date, later ID!)

2. **Possible duplicate**:
   - ID 60303: "Ccv Mooca" on June 12, Ref3 = 558.44
   - ID 60333: "Mooca" on June 12, Ref3 = 558.44
   - Same date, similar description, same balance - likely duplicate

3. **Missing transactions**: The 45.86 euro gap suggests at least one missing transaction

## Re-Import Process

### Step 1: Backup Current June Data

```bash
cd backend
python export_june_revolut.py
```

This creates a CSV backup file: `june_revolut_backup_YYYYMMDD_HHMMSS.csv`

### Step 2: Identify Transaction IDs to Delete

```bash
python identify_june_transactions.py
```

This will show:

- All June Revolut transaction IDs
- Date range
- Total count
- SQL DELETE statement

### Step 3: Delete June Transactions

**IMPORTANT**: Review the transaction IDs carefully before deleting!

```bash
python delete_june_revolut.py
```

Or manually in MySQL:

```sql
DELETE FROM mutaties
WHERE Ref1 = 'NL08REVO7549383472'
AND TransactionDate >= '2025-06-01'
AND TransactionDate < '2025-07-01';
```

### Step 4: Re-Import June Data

1. **Get fresh Revolut export** for June 2025
2. **Ensure data is sorted by date/time** before import
3. **Import using your normal Revolut import process**
4. **Verify the import** using the balance check

### Step 5: Verify the Fix

```bash
# Check balance gaps again
curl "http://localhost:5000/api/banking/check-revolut-balance?iban=NL08REVO7549383472&account_code=1022&start_date=2025-05-01&expected_balance=262.54"

# Check first 10 transactions
curl "http://localhost:5000/api/banking/check-revolut-balance-debug?iban=NL08REVO7549383472&account_code=1022&start_date=2025-05-01&expected_balance=262.54"
```

Expected results:

- First 10 transactions: 0.00 discrepancy ✓
- June transactions: 0.00 discrepancy ✓
- Final balance: Should match expected 262.54

## Important Notes

1. **Backup first**: Always export before deleting
2. **Check IDs**: Verify you're deleting the right transactions
3. **Sort on import**: Ensure new data is chronologically sorted
4. **Verify after**: Run balance check to confirm fix
5. **Keep backup**: Don't delete the CSV backup file

## Troubleshooting

### If discrepancies persist after re-import:

1. Check if there are still missing transactions
2. Verify Ref3 values match bank statement
3. Check for duplicates (same date, amount, description)
4. Ensure all transactions have correct IBAN (NL08REVO7549383472)

### If you need to restore:

Use the CSV backup to manually re-insert transactions if needed.

## Scripts Available

- `export_june_revolut.py` - Backup June transactions to CSV
- `identify_june_transactions.py` - List all June transaction IDs
- `delete_june_revolut.py` - Delete June transactions (with confirmation)
- `check_duplicates.py` - Find potential duplicate transactions
