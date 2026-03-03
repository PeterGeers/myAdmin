# Root Cause Analysis - Opening Balance vs Aangifte IB Differences

## The Correct Model (CONFIRMED)

### Aangifte IB (Current Production - No Year-End Closure)

```sql
-- Balance sheet: Cumulative from ALL history
WHERE VW = 'N' AND TransactionDate <= '2025-12-31'

-- P&L: Only current year
WHERE VW = 'Y' AND YEAR(TransactionDate) = 2025
```

### Year-End Closure (After Migration - With Opening Balances)

```sql
-- Balance sheet: Only current year (includes OpeningBalance)
WHERE VW = 'N' AND YEAR(TransactionDate) = 2025

-- P&L: Only current year
WHERE VW = 'Y' AND YEAR(TransactionDate) = 2025
```

## Why They Should Be DIFFERENT

**Aangifte IB 2025**: Shows cumulative balance from beginning of time through 2025

- Example: Account 3080 = €-228,591.51 (all history)

**OpeningBalance 2026**: Shows OpeningBalance 2025 + 2025 transactions only

- Example: Account 3080 = OpeningBalance 2025 + 2025 activity

**The difference represents transactions from BEFORE 2025.** as the result of the history is stored in the OpeneingBalance record

## Key Findings

### 1. Invalid Transaction: Account 2001 → 2001

**Problem:** Opening balance created transaction with Debet=2001, Credit=2001.

**Fix Applied:** Use equity account as offset when account == interim_account.
** Better fix ** Always use equity account to map all other balance accounts. And do not use the value of the previous equity account (Equity should always be equal to the negative Sum of the other balance accounts). So no use of the interim account.

### 2. Accounts 2030 & 2040 Show Balances

**Need to investigate:** Why do these accounts have balances in 2025 if they're no longer used?
**Hopefully** This is due to some eerrors now in the model. Recheck later

### 3. Amount Differences Are Expected

NOTE: Using the production system tables mutaties and vw_mutaties with the existing logic should have the same results as created by the new logic and the year_end_closure created extra records on the table mutaties and vw_mutaties

NOTEL: I disagree with the next sentence:
The differences between Aangifte IB and OpeningBalance are EXPECTED because:

- Aangifte IB = cumulative (all history)
- OpeningBalance = current year only (after migration)

## Code Changes Applied

1. **Fixed 2001→2001 bug** in `_create_opening_balances()`
2. **Changed `_get_ending_balances()`** to use `YEAR(TransactionDate) = year`
3. **Changed `_count_balance_sheet_accounts()`** to match

## Next Steps

1. Restart backend: `docker-compose restart backend`
2. Reopen year 2025
3. Re-close year 2025 to test fixes
4. Verify OpeningBalance 2026 is calculated correctly
5. Check why accounts 2030 & 2040 have balances



Perfect! Now let's plan the fix properly. Let me outline the approach:

Fix Strategy
1. Fix _create_opening_balances() in year_end_service.py
Current problem: Uses interim account (2001) as offset, which creates invalid transactions when 2001 itself has a balance.

New approach:

Calculate equity as: -(sum of all other balance sheet accounts)
Create opening balance entries using equity account as offset for ALL accounts
Don't create a separate entry for equity account (it's calculated, not stored)
Logic:

# For each non-equity balance sheet account:
if balance > 0:
    Debet: account
    Credit: equity_account
else:
    Debet: equity_account
    Credit: account
2. Verify _get_ending_balances() is correct
Current code (after my changes): Uses YEAR(TransactionDate) = year

This is CORRECT for ongoing closure (after migration).

But we need to check: Is this the first closure (no OpeningBalance exists yet)? If so, use cumulative approach.

3. Files Already Modified
✅ 
year_end_service.py
 - Main closure logic (exists) ✅ 
year_end_routes.py
 - API endpoints (exists) ✅ Frontend components - Year closure UI (exists)

4. Files NOT Yet Modified (from requirements)
❌ mutaties_cache.py - Still uses old logic, needs to support both models ❌ financial_report_generator.py - May need updates ❌ xlsx_export.py - May need updates ❌ Migration script - Needs to be created for historical data

Proposed Fix Order
First: Fix _create_opening_balances() to use equity account properly
Second: Add logic to detect if OpeningBalance exists (use YEAR vs cumulative)
Third: Test by reopening and reclosing year 2025
Fourth: Update cache/reports if needed
Fifth: Create migration script for historical data
Questions Before We Start
Should we always calculate equity as negative sum of other accounts? Or should we also read the actual equity balance and use whichever is correct?

For the first year closure (no OpeningBalance exists): Should we automatically detect this and use cumulative approach, or require a flag?

Do we need to update mutaties_cache.py now, or can that wait until after we verify the closure logic works?

What do you think? Should we start with fixing _create_opening_balances() first?